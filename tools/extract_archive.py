#!/usr/bin/env python3
"""Extrait, pour chaque version archivée du client Allods Online, l'écran de
lancement du menu principal, son logo et son thème musical (page « Chroniques »).

Pour chaque version décrite dans `tools/clients_manifest.json` :

* **écran de lancement** — la vidéo de menu (`Video/<N>_0Events/MainMenu/MainMenu.ogv`)
  quand le client en possède une, transcodée en `menu.webm` + `menu.mp4` (avec
  `intro.*` si une intro existe) ; sinon `background.png`. Jusqu'à la 8.0 le vrai
  menu est une scène 3D que le client ne stocke pas comme image : le fond est
  alors une **capture d'écran** du jeu (`background.capture`, p. ex.
  `refs/menu-3.0.png`, voir `tools/capture_game.ps1`). Tant que la capture
  n'existe pas, on retombe sur la texture de repli du client
  (`Interface/Wrap/MainMenu/Main2/Background*.(UITexture).bin`, décodée par
  `tools.uitexture`) et l'entrée d'index porte `background_note`. Les clients 1.x
  n'ont pas de fond unique mais un empilement (ciel + héros gauche/droite +
  vaisseaux) : le manifeste décrit alors des `layers` que l'on compose ici (voir
  `compose_background`).
* **logo** — la texture `Interface/Common/Elements/WrapAllodsLogo/WrapAllodsLogoV<N>`
  de l'add-on, dans la meilleure langue disponible (`fra` > `eng_eu`/`eng` > non
  localisée, voir `LOGO_LOCALES`), détourée en `logo.png`. Les versions dont
  aucun client archivé ne conserve le logo n'ont pas de clé `logo` : la page
  affiche le titre en toutes lettres.
* **thème musical** — la banque `SFX/Music/Music_Menu.fsb` du client, dont on
  énumère les subsongs avec vgmstream ; `pick_theme_subsong` choisit le thème
  (`MainMenu*` > `MainTitle` > `Menu*` > la plus longue) sauf si `theme.prefer`
  le nomme, décodé puis encodé en `theme.ogg` + `theme.mp3` (mêmes réglages que
  `tools/extract_audio.py`). `theme: null` (+ `theme_note`) = version dont aucun
  client archivé ne conserve le thème : on n'en invente pas.

Sorties : `public/game/archive/<version>/…`, l'emblème de chargement commun
(`public/game/archive/_common/`) et l'index `public/game/archive.json` (tableau
trié par version : `{version, name?, label, media, background?, background_note?,
logo?, video?, intro?, theme?, note?, theme_note?}`).

Idempotent : une version dont les sorties existent déjà est ignorée (son entrée
d'index est reprise de l'index précédent), sauf `--force` — à une exception près,
la capture d'écran d'un fond, recopiée à chaque passage (c'est une seconde de
travail, et c'est ce qui fait basculer une version de l'illustration de repli à
sa vraie capture dès que le fichier apparaît). Un client absent (les disques
externes ne sont pas toujours montés) ou une entrée introuvable déclenche un
avertissement sur stderr et laisse une entrée `media: null` : la page Chroniques
sait afficher « Média non extrait ».

Usage : python3 tools/extract_archive.py [--only 8.0 --only 9.0] [--force]
                                         [--skip-video] [--skip-intro]
                                         [--client-root-override 8.0=/mnt/x/...]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.extract_audio import (  # noqa: E402
    DEFAULT_VGMSTREAM,
    encode_outputs,
    extract_pak_entry_bytes,
    fsb_payload_from_bytes,
    probe_duration,
    run_vgmstream,
)
from tools.uitexture import decode_uitexture, trim_transparent_padding  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "clients_manifest.json"
# Build WebAssembly de vgmstream, seule capable de décoder les banques CELT (clients 3.0/4.0).
DEFAULT_VGMSTREAM_WASM = DEFAULT_VGMSTREAM.parent.parent / "vgmstream_wasm" / "vgmstream-node-wrapper.js"
DEFAULT_OUT = HERE.parent / "public" / "game" / "archive"
# Racine des captures d'écran du manifeste (`background.capture`), relatives au dépôt.
REPO_ROOT = HERE.parent
DEFAULT_CANVAS = (1920, 1080)

# Ordre des clés de chaque entrée d'index (spec § 3), pour un JSON lisible en diff.
KEY_ORDER = ("version", "name", "label", "media", "duration", "background", "background_note",
             "logo", "video", "intro", "theme", "note", "theme_note")
ALWAYS_KEYS = ("version", "label", "media")

# Langues du logo, de la meilleure à la moins bonne ; `None` = texture non localisée (russe).
LOGO_LOCALES = ("fra", "fr", "eng_eu", "eng", None)
TEXTURE_SUFFIX = ".(UITexture).bin"

# Fond affiché tant que la capture de la scène 3D du menu n'a pas été fournie.
CAPTURE_PENDING_NOTE = "capture de la scène 3D à venir (illustration de repli)"

_FSB5_MAGIC = b"FSB5"


# --- choix du thème -----------------------------------------------------------------------

def _stem(name: str) -> str:
    """Nom du subsong sans extension : les banques FSB4 (clients 1.x/2.x) gardent « .wav »/« .mp3 »."""
    return re.sub(r"\.(wav|mp3|ogg|fsb)$", "", (name or "").strip(), flags=re.IGNORECASE)


def theme_rank(name: str) -> int:
    """Priorité d'un subsong comme thème du menu (0 = meilleur)."""
    stem = _stem(name)
    low = stem.lower()
    if low.startswith("mainmenu"):
        return 0
    if low == "maintitle":
        return 1
    if low.startswith("menu"):
        return 2
    return 3


def pick_theme_subsong(streams: list[dict]) -> int:
    """Renvoie l'index (1-based, tel que le prend vgmstream) du subsong « thème du menu ».

    Préférence par nom — `MainMenu*` (le thème de l'add-on courant), puis
    `MainTitle` (le thème générique des vieux clients), puis `Menu*`
    (`MenuAmbient`). À rang égal, on écarte d'abord les pistes à plus de deux
    canaux : les `MainMenu_adaptive` sont des empilements de calques d'intensité
    (4 canaux) que le moteur mixe, pas des thèmes jouables tels quels ; puis on
    garde la plus longue, qui est celle de l'add-on courant quand la banque en
    conserve plusieurs (le client 16.0 garde encore le thème du 15.0). Une
    banque sans aucun nom reconnu retombe sur la piste la plus longue.
    """
    if not streams:
        raise ValueError("banque vide : aucun subsong à choisir")
    best = min(
        streams,
        key=lambda s: (
            theme_rank(s.get("name", "")),
            1 if int(s.get("channels") or 2) > 2 else 0,
            -float(s.get("duration") or 0.0),
            int(s["index"]),
        ),
    )
    return int(best["index"])


# --- index --------------------------------------------------------------------------------

def version_key(version: str) -> tuple[int, ...]:
    """Clé de tri numérique : « 9.0 » doit précéder « 10.0 »."""
    return tuple(int(p) for p in re.findall(r"\d+", str(version))) or (0,)


def build_label(name: str | None, version: str) -> str:
    """Libellé affiché : « Allods Online - Game of Gods (3.0) ».

    Le manifeste ne porte que le nom de l'add-on (`name`) ; les versions qui n'en
    ont pas (1.1, avant les add-ons) donnent « Allods Online (1.1) ».
    """
    name = (name or "").strip()
    return f"Allods Online - {name} ({version})" if name else f"Allods Online ({version})"


def build_index(entries: list[dict]) -> list[dict]:
    """Trie les entrées par version et n'en garde que les clés renseignées.

    `media` est conservé même à `null` : c'est ce qui signale à la page une
    version dont le média n'a pas pu être extrait.
    """
    index = []
    for entry in sorted(entries, key=lambda e: version_key(e["version"])):
        index.append({k: entry.get(k) for k in KEY_ORDER if k in ALWAYS_KEYS or entry.get(k) is not None})
    return index


# --- fond statique ------------------------------------------------------------------------

def _decode_texture(data: bytes) -> Image.Image:
    img, _info = decode_uitexture(data)
    return trim_transparent_padding(img)


def compose_background(layers: list[tuple[Image.Image, dict]], canvas: tuple[int, int] = DEFAULT_CANVAS) -> Image.Image:
    """Empile les calques d'un fond de menu sur un cadre de taille `canvas`.

    Les menus des clients 1.x sont composés : un ciel étiré sur tout l'écran
    (`fit: "cover"`), les vaisseaux ancrés en haut et les héros des deux
    factions ancrés en bas à gauche et en bas à droite. `anchor` accepte
    `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center` ; `scale`
    (optionnel) redimensionne le calque avant l'ancrage.
    """
    out = Image.new("RGBA", canvas, (0, 0, 0, 255))
    for img, spec in layers:
        img = img.convert("RGBA")
        if spec.get("fit") == "cover":
            img = img.resize(canvas, Image.LANCZOS)
        elif spec.get("scale"):
            scale = float(spec["scale"])
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        anchor = spec.get("anchor", "top-left")
        if spec.get("fit") == "cover":
            x = y = 0
        else:
            x = 0 if "left" in anchor else canvas[0] - img.width if "right" in anchor else (canvas[0] - img.width) // 2
            y = 0 if "top" in anchor else canvas[1] - img.height if "bottom" in anchor else (canvas[1] - img.height) // 2
        out.alpha_composite(img, (x + int(spec.get("dx", 0)), y + int(spec.get("dy", 0))))
    return out


def write_background(data: bytes, spec: dict, pak_path: Path, target: Path) -> str | None:
    """Écrit `background.png`. Renvoie None en cas de succès, sinon le message d'erreur.

    `data` sont les octets de l'entrée principale (le fond simple, ou le premier
    calque) ; `pak_path` sert à relire les calques suivants d'un fond composé.
    """
    try:
        layers_spec = spec.get("layers")
        if layers_spec:
            layers = []
            for i, layer in enumerate(layers_spec):
                raw = data if i == 0 else extract_pak_entry_bytes(pak_path, layer["entry"])
                if raw is None:
                    return f"calque introuvable : {layer['entry']}"
                layers.append((_decode_texture(raw), layer))
            img = compose_background(layers, tuple(spec.get("canvas", DEFAULT_CANVAS)))
        else:
            img = _decode_texture(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(target)
    except Exception as exc:  # décodage DXT, Pillow, disque…
        return f"{type(exc).__name__} : {exc}"
    return None


def write_capture(source: Path, target: Path) -> str | None:
    """Recopie une capture d'écran du jeu en `background.png` (aucun recadrage).

    Les captures sont prises sur la zone client du jeu (1920 × 1009 avec
    `tools/capture_game.ps1`) : on ne recadre rien et on ne redimensionne rien,
    la page les affiche en `object-fit: cover`. Renvoie None, ou l'erreur.
    """
    try:
        with Image.open(source) as img:
            target.parent.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").save(target)
    except Exception as exc:  # fichier tronqué, format inconnu, disque…
        return f"{type(exc).__name__} : {exc}"
    return None


# --- logo ---------------------------------------------------------------------------------

def logo_candidates(entry: str) -> list[str]:
    """Entrées de pak à essayer pour un logo, de la meilleure langue à la moins bonne.

    `entry` est le chemin de la texture sans locale ni suffixe
    (`…/WrapAllodsLogoV16`) : le client range chaque traduction dans un fichier
    distinct (`….fra.(UITexture).bin`), la version non localisée étant le russe.
    """
    return [f"{entry}.{loc}{TEXTURE_SUFFIX}" if loc else f"{entry}{TEXTURE_SUFFIX}" for loc in LOGO_LOCALES]


def extract_logo(spec: dict, root: Path, target: Path, force: bool) -> tuple[str | None, str | None]:
    """Écrit `logo.png` (détouré, alpha conservé). Renvoie (nom du fichier, erreur).

    `spec.pak` accepte un pak ou une liste de paks : les logos récents vivent
    dans les `BaseLoc<langue>_x64.pak`, les anciens dans `Interface.Mini.pak`. La
    langue prime sur l'ordre des paks — on cherche d'abord la variante française
    partout, puis l'anglaise, etc.
    """
    if target.exists() and not force:
        return target.name, None
    paks = spec["pak"] if isinstance(spec["pak"], list) else [spec["pak"]]
    for candidate in logo_candidates(spec["entry"]):
        for pak in paks:
            data = extract_pak_entry_bytes(root / pak, candidate)
            if data is None:
                continue
            try:
                img = _decode_texture(data)
                target.parent.mkdir(parents=True, exist_ok=True)
                img.convert("RGBA").save(target)
            except Exception as exc:  # décodage DXT, Pillow, disque…
                return None, f"logo illisible ({candidate}) : {type(exc).__name__} : {exc}"
            return target.name, None
    return None, f"logo introuvable : {spec['entry']} dans {', '.join(paks)}"


def extract_logo_from_url(spec: dict, target: Path, force: bool) -> tuple[str | None, str | None]:
    """Logo publié par l'éditeur (site/forum allods.my.games) quand aucun client archivé
    ne conserve la texture : `logo: {url, note?}`. Le PNG est détouré de son padding
    transparent comme les textures du client. Renvoie (nom du fichier, erreur)."""
    if target.exists() and not force:
        return target.name, None
    with tempfile.TemporaryDirectory(prefix="allodex-archive-") as tmp:
        src = Path(tmp) / "logo-source"
        try:
            download(spec["url"], src)
            with Image.open(src) as img:
                out = trim_transparent_padding(img.convert("RGBA"))
                target.parent.mkdir(parents=True, exist_ok=True)
                out.save(target)
        except (OSError, ValueError) as exc:
            return None, f"logo introuvable : {spec['url']} ({exc})"
    return target.name, None


def extract_common(manifest: dict, out_dir: Path, overrides: dict, force: bool, report: list[str]) -> None:
    """Extrait les textures communes à toutes les versions dans `<out>/_common/`.

    L'emblème du bas de l'écran de lancement (`LoadingGlobeFront` + `LoadingCyclone`)
    est identique des clients 9.0 à 17.0 : un seul jeu de fichiers, pas un par version.
    """
    spec = manifest.get("common")
    if not spec:
        return
    key = spec.get("client", "")
    root = Path(overrides.get(key) or manifest.get("clients", {}).get(key, {}).get("root", ""))
    targets = {name: out_dir / "_common" / name for name in spec.get("textures", {})}
    if not force and all(t.exists() for t in targets.values()):
        return
    if not root.is_dir():
        report.append(f"AVERTISSEMENT : _common — client absent : {root}")
        return
    pak_path = root / spec["pak"]
    for name, entry in spec.get("textures", {}).items():
        target = targets[name]
        if target.exists() and not force:
            continue
        data = extract_pak_entry_bytes(pak_path, entry)
        if data is None:
            report.append(f"AVERTISSEMENT : _common — texture introuvable : {entry} dans {pak_path}")
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _decode_texture(data).convert("RGBA").save(target)
        except Exception as exc:  # décodage DXT, Pillow, disque…
            report.append(f"AVERTISSEMENT : _common — texture illisible ({entry}) : {type(exc).__name__} : {exc}")
            continue
        print(f"_common  {name}")


# --- vidéo --------------------------------------------------------------------------------

def _ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué (code {result.returncode}) : {result.stderr.decode(errors='replace')[:300]}")


def transcode_video(src: Path, out_base: Path) -> None:
    """Transcode un `.ogv` du client en WebM/VP9 + MP4/H.264, sans piste audio.

    Le VP9 par défaut met plusieurs minutes par clip : `-cpu-used 4 -row-mt 1`
    ramène un fond de menu sous les dix secondes. Le débit est piloté au CRF
    (`-b:v 0`) et non à 2500 kb/s comme dans `extract_assets.py` : à débit
    imposé, VP9 en mode temps réel produisait 4,5 Mo pour dix secondes de boucle,
    contre 0,6 Mo au CRF 32 sans différence visible derrière l'interface.
    """
    base = ["-i", str(src), "-an"]
    _ffmpeg(base + ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
                    "-deadline", "good", "-cpu-used", "4", str(out_base.with_suffix(".webm"))])
    _ffmpeg(base + ["-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(out_base.with_suffix(".mp4"))])


def extract_video(data: bytes, out_base: Path) -> tuple[float, str | None]:
    """Écrit `<out_base>.webm` et `.mp4`. Renvoie (durée, erreur éventuelle)."""
    out_base.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="allodex-archive-") as tmp:
        src = Path(tmp) / "source.ogv"
        src.write_bytes(data)
        try:
            transcode_video(src, out_base)
        except RuntimeError as exc:
            return 0.0, str(exc)
        return probe_duration(src), None


# --- thème --------------------------------------------------------------------------------

def fsb_subsong_count(payload: bytes) -> int | None:
    """Nombre de subsongs d'une banque FMOD.

    `tools/extract_audio.py` lit toujours l'entier en 8..12, ce qui n'est vrai
    que pour FSB5 ; les banques FSB4 des clients 1.x/2.x mettent le nombre
    d'échantillons en 4..8 (8..12 y est la taille de la table d'en-têtes).
    """
    if len(payload) < 12:
        return None
    if payload[:4] == _FSB5_MAGIC:
        return int.from_bytes(payload[8:12], "little")
    if payload[:3] == b"FSB":
        return int.from_bytes(payload[4:8], "little")
    return None


def _parse_metadata(text: str) -> dict:
    """Extrait nom, longueur et nombre de subsongs d'une sortie `vgmstream-cli -m`.

    La longueur retenue est « stream total samples » et non « play duration » :
    sur une banque bouclée (le thème du client 4.0), `play duration` compte les
    boucles jouées (6:56) alors que le WAV décodé avec `-i` fait la longueur du
    flux (3:34).
    """
    name = re.search(r"^stream name:\s*(.+)$", text, re.MULTILINE)
    samples = re.search(r"^stream total samples:\s*(\d+)", text, re.MULTILINE) or re.search(
        r"^play duration:\s*(\d+) samples", text, re.MULTILINE)
    rate = re.search(r"^sample rate:\s*(\d+) Hz", text, re.MULTILINE)
    count = re.search(r"^stream count:\s*(\d+)", text, re.MULTILINE)
    channels = re.search(r"^channels:\s*(\d+)", text, re.MULTILINE)
    duration = 0.0
    if samples and rate and int(rate.group(1)):
        duration = round(int(samples.group(1)) / int(rate.group(1)), 3)
    return {
        "name": name.group(1).strip() if name else "",
        "duration": duration,
        "count": int(count.group(1)) if count else None,
        "channels": int(channels.group(1)) if channels else 2,
    }


def vgmstream_metadata(vgmstream: Path, fsb_path: Path, subsong: int) -> dict:
    result = subprocess.run([str(vgmstream), "-m", "-s", str(subsong), str(fsb_path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"vgmstream -m a échoué (subsong {subsong}) : {result.stderr.strip()[:200]}")
    return _parse_metadata(result.stdout)


def list_subsongs(vgmstream: Path, fsb_path: Path, payload: bytes) -> list[dict]:
    """Énumère les subsongs d'une banque : [{index, name, duration, channels}]."""
    first = vgmstream_metadata(vgmstream, fsb_path, 1)
    count = first.get("count") or fsb_subsong_count(payload) or 1
    streams = [{"index": 1, "name": first["name"], "duration": first["duration"], "channels": first["channels"]}]
    for i in range(2, count + 1):
        meta = vgmstream_metadata(vgmstream, fsb_path, i)
        streams.append({"index": i, "name": meta["name"], "duration": meta["duration"], "channels": meta["channels"]})
    return streams


def decode_subsong(vgmstream: Path, wasm: Path | None, fsb: Path, subsong: int, wav: Path) -> None:
    """Décode un subsong en WAV, avec repli sur la build WebAssembly de vgmstream.

    Les banques des clients 3.0 et 4.0 sont encodées en « Custom CELT » (FMOD) :
    le binaire natif `vgmstream-cli` livré avec le projet segfault (code -11) sur
    ce codec, alors que la build WASM (`vgmstream_wasm/vgmstream-node-wrapper.js`,
    exécutée par node) les décode correctement. On n'y recourt qu'en second,
    car elle est nettement plus lente.
    """
    try:
        run_vgmstream(vgmstream, fsb, subsong, wav)
        return
    except RuntimeError:
        if wasm is None or not Path(wasm).exists() or shutil.which("node") is None:
            raise
    cmd = ["node", str(wasm), "-i", "-s", str(subsong), "-o", str(wav), str(fsb)]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0 or not wav.exists():
        stderr = (result.stderr or b"").decode(errors="replace").strip()[:300]
        raise RuntimeError(f"vgmstream (WASM) a échoué (code {result.returncode}) : {stderr}")


def probe_channels(path: Path) -> int:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 2


def fold_to_stereo(wav: Path) -> Path:
    """Ne garde que la première paire stéréo d'un subsong à calques.

    Les thèmes « MainMenu_adaptive » sont des pistes FMOD à deux calques (4
    canaux) : les calques sont des variantes d'intensité destinées à être mixées
    par le jeu, pas des canaux surround. Les sommer donnerait une bouillie, on
    garde donc le premier calque (équivalent de `vgmstream-cli -2 0`).
    """
    if probe_channels(wav) <= 2:
        return wav
    folded = wav.with_name("stereo.wav")
    _ffmpeg(["-i", str(wav), "-filter_complex", "[0:a]pan=stereo|c0=c0|c1=c1[a]", "-map", "[a]", str(folded)])
    return folded


def extract_theme(spec: dict, root: Path, out_dir: Path, vgmstream: Path, force: bool,
                  wasm: Path | None = None) -> tuple[dict | None, str | None]:
    """Décode le thème du menu vers `theme.ogg`/`theme.mp3`. Renvoie (entrée d'index, erreur)."""
    pak_path = root / spec["pak"]
    data = extract_pak_entry_bytes(pak_path, spec["entry"])
    if data is None:
        return None, f"banque introuvable : {spec['entry']} dans {pak_path}"
    payload = fsb_payload_from_bytes(data, spec["entry"])
    if payload is None:
        return None, f"banque FMOD non reconnue : {spec['entry']}"

    with tempfile.TemporaryDirectory(prefix="allodex-archive-") as tmp:
        fsb = Path(tmp) / "bank.fsb"
        fsb.write_bytes(payload)
        try:
            streams = list_subsongs(vgmstream, fsb, payload)
        except RuntimeError as exc:
            return None, str(exc)
        if not streams:
            return None, f"banque sans subsong : {spec['entry']}"

        prefer = spec.get("prefer")
        chosen = None
        if prefer:
            chosen = next((s for s in streams if _stem(s["name"]) == prefer), None)
        subsong = chosen["index"] if chosen else pick_theme_subsong(streams)
        picked = next(s for s in streams if s["index"] == subsong)

        out_base = out_dir / "theme"
        if not (out_base.with_suffix(".ogg").exists() and out_base.with_suffix(".mp3").exists() and not force):
            wav = Path(tmp) / "theme.wav"
            try:
                decode_subsong(vgmstream, wasm, fsb, subsong, wav)
            except RuntimeError as exc:
                return None, str(exc)
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                encode_outputs(fold_to_stereo(wav), out_base, "tracks")
            except RuntimeError as exc:
                return None, str(exc)

    return {
        "name": _stem(picked["name"]) or f"subsong {subsong}",
        "subsong": subsong,
        "duration": probe_duration(out_base.with_suffix(".ogg")) or picked["duration"],
        "ogg": "theme.ogg",
        "mp3": "theme.mp3",
        "alternatives": [_stem(s["name"]) for s in streams if s["index"] != subsong and s["name"]],
    }, None


def download(url: str, target: Path) -> None:
    """Télécharge `url` dans `target` (User-Agent de navigateur : allods.ru refuse le défaut)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Allodex)"})
    with urllib.request.urlopen(req, timeout=60) as resp, target.open("wb") as out:
        shutil.copyfileobj(resp, out)


def extract_theme_from_url(spec: dict, out_dir: Path, force: bool) -> tuple[dict | None, str | None]:
    """Thème publié par l'éditeur (bande originale d'allods.ru) quand aucun client ne le
    conserve : `theme: {url, name, note?}`. Le MP3 est téléchargé puis réencodé en
    `theme.ogg`/`theme.mp3` comme les banques FMOD. Renvoie (entrée d'index, erreur)."""
    out_base = out_dir / "theme"
    if not (out_base.with_suffix(".ogg").exists() and out_base.with_suffix(".mp3").exists() and not force):
        with tempfile.TemporaryDirectory(prefix="allodex-archive-") as tmp:
            src = Path(tmp) / "theme-source"
            try:
                download(spec["url"], src)
            except (OSError, ValueError) as exc:
                return None, f"téléchargement impossible : {spec['url']} ({exc})"
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                encode_outputs(src, out_base, "tracks")
            except RuntimeError as exc:
                return None, str(exc)
    return {
        "name": spec.get("name") or Path(spec["url"]).stem,
        "duration": probe_duration(out_base.with_suffix(".ogg")),
        "ogg": "theme.ogg",
        "mp3": "theme.mp3",
        "source": spec["url"],
    }, None


# --- pilotage -----------------------------------------------------------------------------

def _client_root(manifest: dict, version_spec: dict, spec: dict, overrides: dict) -> Path:
    key = spec.get("client") or version_spec.get("client") or version_spec["version"]
    root = overrides.get(key) or manifest.get("clients", {}).get(key, {}).get("root", "")
    return Path(root)


def _note(*parts: str | None) -> str | None:
    kept = [p for p in parts if p]
    return " ; ".join(kept) if kept else None


def process_version(
    version_spec: dict,
    manifest: dict,
    out_dir: Path,
    vgmstream: Path,
    force: bool,
    skip_video: bool,
    skip_intro: bool,
    overrides: dict,
    previous: dict,
    report: list[str],
    wasm: Path | None = None,
    capture_root: Path | None = None,
) -> dict:
    version = version_spec["version"]
    entry = {
        "version": version,
        "name": version_spec.get("name"),
        "label": build_label(version_spec.get("name"), version),
        "media": None,
        "theme_note": version_spec.get("theme_note"),
    }
    problems: list[str] = []
    ver_dir = out_dir / version
    capture_root = Path(capture_root) if capture_root else REPO_ROOT

    video_spec = version_spec.get("video")
    bg_spec = version_spec.get("background")
    logo_spec = version_spec.get("logo")
    theme_spec = version_spec.get("theme")

    # -- média
    if video_spec and not skip_video:
        root = _client_root(manifest, version_spec, video_spec, overrides)
        if not root.is_dir():
            problems.append(f"client absent : {root}")
            report.append(f"AVERTISSEMENT : {version} — client absent : {root}")
        else:
            pak_path = root / video_spec["pak"]
            for kind, key, base in (("menu", "entry", "menu"), ("intro", "intro", "intro")):
                name = video_spec.get(key)
                if not name or (kind == "intro" and skip_intro):
                    continue
                out_base = ver_dir / base
                if out_base.with_suffix(".webm").exists() and out_base.with_suffix(".mp4").exists() and not force:
                    entry["media"] = "video"
                    entry["video" if kind == "menu" else "intro"] = {"webm": f"{base}.webm", "mp4": f"{base}.mp4"}
                    if kind == "menu":
                        entry["duration"] = (previous.get("duration") if previous else None) or probe_duration(out_base.with_suffix(".mp4"))
                    continue
                data = extract_pak_entry_bytes(pak_path, name)
                if data is None:
                    problems.append(f"vidéo introuvable : {name}")
                    report.append(f"AVERTISSEMENT : {version} — vidéo introuvable : {name} dans {pak_path}")
                    continue
                duration, err = extract_video(data, out_base)
                if err:
                    problems.append(f"transcodage impossible ({name}) : {err}")
                    report.append(f"AVERTISSEMENT : {version} — transcodage impossible : {err}")
                    continue
                entry["media"] = "video"
                entry["video" if kind == "menu" else "intro"] = {"webm": f"{base}.webm", "mp4": f"{base}.mp4"}
                if kind == "menu":
                    entry["duration"] = duration
                print(f"{version:>5}  {base}.webm / {base}.mp4  ({duration:.1f}s)")
    elif bg_spec:
        root = _client_root(manifest, version_spec, bg_spec, overrides)
        target = ver_dir / "background.png"
        # Capture de la scène 3D du menu : elle prime sur la texture de repli, et on
        # la recopie à chaque passage pour qu'elle remplace le repli dès qu'elle arrive.
        capture = capture_root / bg_spec["capture"] if bg_spec.get("capture") else None
        if capture is not None and capture.is_file():
            err = write_capture(capture, target)
            if err:
                problems.append(f"capture illisible ({capture}) : {err}")
                report.append(f"AVERTISSEMENT : {version} — capture illisible ({capture}) : {err}")
            else:
                entry["media"] = "image"
                entry["background"] = "background.png"
                print(f"{version:>5}  background.png (capture {capture.name})")
        elif capture is not None:
            entry["background_note"] = CAPTURE_PENDING_NOTE

        # Pas (ou plus) de capture : texture de repli du client, sauf si elle est déjà là.
        if entry["media"] == "image":
            pass  # la capture a fait le travail
        elif target.exists() and not force:
            entry["media"] = "image"
            entry["background"] = "background.png"
        elif not root.is_dir():
            problems.append(f"client absent : {root}")
            report.append(f"AVERTISSEMENT : {version} — client absent : {root}")
        else:
            pak_path = root / bg_spec["pak"]
            main_entry = bg_spec.get("entry") or bg_spec["layers"][0]["entry"]
            data = extract_pak_entry_bytes(pak_path, main_entry)
            if data is None:
                problems.append(f"fond introuvable : {main_entry}")
                report.append(f"AVERTISSEMENT : {version} — fond introuvable : {main_entry} dans {pak_path}")
            else:
                err = write_background(data, bg_spec, pak_path, target)
                if err:
                    problems.append(f"fond illisible : {err}")
                    report.append(f"AVERTISSEMENT : {version} — fond illisible ({main_entry}) : {err}")
                else:
                    entry["media"] = "image"
                    entry["background"] = "background.png"
                    print(f"{version:>5}  background.png")

    # -- logo de l'add-on
    if logo_spec and logo_spec.get("url"):
        logo, err = extract_logo_from_url(logo_spec, ver_dir / "logo.png", force)
        if err:
            problems.append(err)
            report.append(f"AVERTISSEMENT : {version} — {err}")
        else:
            entry["logo"] = logo
            print(f"{version:>5}  logo.png (allods.my.games)")
    elif logo_spec:
        root = _client_root(manifest, version_spec, logo_spec, overrides)
        if not root.is_dir():
            msg = f"client absent : {root}"
            if msg not in problems:
                problems.append(msg)
                report.append(f"AVERTISSEMENT : {version} — logo : client absent : {root}")
        else:
            logo, err = extract_logo(logo_spec, root, ver_dir / "logo.png", force)
            if err:
                problems.append(err)
                report.append(f"AVERTISSEMENT : {version} — {err}")
            else:
                entry["logo"] = logo
                print(f"{version:>5}  logo.png")

    # -- thème
    if theme_spec and theme_spec.get("url"):
        theme, err = extract_theme_from_url(theme_spec, ver_dir, force)
        if err:
            problems.append(f"thème indisponible : {err}")
            report.append(f"AVERTISSEMENT : {version} — thème indisponible : {err}")
        else:
            entry["theme"] = theme
            print(f"{version:>5}  theme.ogg / theme.mp3  « {theme['name']} » ({theme['duration']:.1f}s, allods.ru)")
    elif theme_spec:
        root = _client_root(manifest, version_spec, theme_spec, overrides)
        if not root.is_dir():
            msg = f"client absent : {root}"
            if msg not in problems:
                problems.append(msg)
                report.append(f"AVERTISSEMENT : {version} — thème : client absent : {root}")
        else:
            theme, err = extract_theme(theme_spec, root, ver_dir, vgmstream, force, wasm)
            if err:
                problems.append(f"thème indisponible : {err}")
                report.append(f"AVERTISSEMENT : {version} — thème indisponible : {err}")
            else:
                entry["theme"] = theme
                print(f"{version:>5}  theme.ogg / theme.mp3  « {theme['name']} » ({theme['duration']:.1f}s)")

    # Rien de neuf cette fois mais une extraction précédente existe : on la garde —
    # sauf ce que le manifeste ne demande plus (un thème retiré du manifeste ne doit
    # pas ressusciter depuis l'index précédent : `theme: null` est une décision).
    declared = {
        "media": bool(video_spec or bg_spec),
        "duration": bool(video_spec),
        "background": bool(bg_spec),
        "video": bool(video_spec),
        "intro": bool(video_spec),
        "logo": bool(logo_spec),
        "theme": bool(theme_spec),
    }
    if previous:
        for key, wanted in declared.items():
            if wanted and entry.get(key) is None and previous.get(key) is not None:
                entry[key] = previous[key]

    entry["note"] = _note(version_spec.get("note"), *problems)
    return entry


def run(
    manifest: dict,
    out_dir: Path,
    vgmstream: Path,
    force: bool = False,
    only: list[str] | None = None,
    skip_video: bool = False,
    skip_intro: bool = False,
    overrides: dict | None = None,
    wasm: Path | None = None,
    capture_root: Path | None = None,
) -> tuple[list[dict], list[str]]:
    out_dir = Path(out_dir)
    index_path = out_dir.parent / f"{out_dir.name}.json"
    previous: dict[str, dict] = {}
    if index_path.exists():
        try:
            previous = {e["version"]: e for e in json.loads(index_path.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            previous = {}

    report: list[str] = []
    extract_common(manifest, out_dir, overrides or {}, force, report)
    entries = []
    for version_spec in manifest.get("versions", []):
        if only and version_spec["version"] not in only:
            # `--only` ne doit pas amputer l'index : on reprend l'entrée précédente.
            kept = previous.get(version_spec["version"])
            if kept:
                entries.append(kept)
            continue
        entries.append(
            process_version(
                version_spec, manifest, out_dir, vgmstream, force, skip_video, skip_intro,
                overrides or {}, previous.get(version_spec["version"], {}), report, wasm, capture_root,
            )
        )
    return build_index(entries), report


def parse_overrides(values: list[str] | None) -> dict:
    overrides = {}
    for raw in values or []:
        if "=" not in raw:
            raise argparse.ArgumentTypeError(f"--client-root-override attend VERSION=CHEMIN, reçu : {raw}")
        key, path = raw.split("=", 1)
        overrides[key.strip()] = path.strip()
    return overrides


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--vgmstream", default=str(DEFAULT_VGMSTREAM))
    p.add_argument("--vgmstream-wasm", default=str(DEFAULT_VGMSTREAM_WASM),
                   help="repli node/WASM pour les banques que le binaire natif ne sait pas décoder")
    p.add_argument("--only", action="append", help="ne traiter que cette version (répétable)")
    p.add_argument("--client-root-override", action="append", metavar="VERSION=CHEMIN",
                   help="remplace la racine du client d'une version (répétable)")
    p.add_argument("--capture-root", default=str(REPO_ROOT),
                   help="racine des captures d'écran de fond du manifeste (`background.capture`)")
    p.add_argument("--force", action="store_true", help="réécrire les sorties existantes")
    p.add_argument("--skip-video", action="store_true", help="ne pas transcoder les vidéos")
    p.add_argument("--skip-intro", action="store_true", help="ne transcoder que la boucle de menu")
    args = p.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERREUR : manifeste introuvable à {manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            print(f"ERREUR : {tool} introuvable dans le PATH", file=sys.stderr)
            return 2

    out_dir = Path(args.out)
    index, report = run(
        manifest, out_dir, Path(args.vgmstream), force=args.force, only=args.only,
        skip_video=args.skip_video, skip_intro=args.skip_intro,
        overrides=parse_overrides(args.client_root_override), wasm=Path(args.vgmstream_wasm),
        capture_root=Path(args.capture_root),
    )

    for line in report:
        print(line, file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir.parent / f"{out_dir.name}.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    complete = sum(1 for e in index if e["media"] and e.get("theme"))
    print(f"OK : {len(index)} version(s) indexée(s) ({complete} complète(s)) dans {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
