"""Effets visuels et sons des exports 3D du client 17.0 (fatalités, cinématiques moteur) :
gabarits d'objets visuels en glTF avec leurs composants, clips et systèmes de particules
(`FxBuild`), particules allégées et atlas réduit (`ParticlePool`), ondes des événements FMOD
(`export_sounds`, `fsb5_stream_names`).

Extrait de `tools/extract_fatalities.py` lors de la réunion des branches ; les fatalités
l'importent. `export_sounds` prend maintenant la liste des banques à fouiller (celles des
fatalités par défaut) et une clé d'appariement optionnelle.
"""
from __future__ import annotations

import re
import struct
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from tools.allods_gltf import Exporter, TexturePool, load_animation, load_geometry, reduce_keys
from tools.allods_packdb import PackDB, PakCatalog
from tools.allods_visdb import STATE_ANIMATION, STATE_STRIDE, VOT_STATES, animation_bounds, read_visobject
from tools.extract_menu_scene import BinSource, read_chunks


# --- effets ------------------------------------------------------------------------------------

_ANIM_NAMES: dict[int, dict[int, str]] = {}

@dataclass
class FxBuild:
    exporter: Exporter
    db: PackDB
    cat: PakCatalog
    bins: BinSource
    names: dict[int, str] = field(default_factory=dict)       # décalage VOT → nom unique
    meta: dict[str, dict] = field(default_factory=dict)
    roots: list[int] = field(default_factory=list)
    sounds: set[str] = field(default_factory=set)
    particles: "ParticlePool | None" = None
    report: list[str] = field(default_factory=list)

    def name_of(self, off: int) -> str:
        if off not in self.names:
            base = read_visobject(self.db, self.cat, off).name
            name, k = base, 2
            while name in self.names.values():
                name, k = f"{base}#{k}", k + 1
            self.names[off] = name
        return self.names[off]

    def default_state(self, state_ids: tuple[int, ...], animation: int | None) -> bool:
        """Un `StateComponent` est-il montré dans l'état par défaut du gabarit : l'une de ses
        animations (énumération `Animations`) est celle du premier état (`KaniaShip.Idle` → `idle`) ;
        sans animation, l'état `idle`."""
        from tools.allods_visdb import animation_names
        root = getattr(self.db, "parent", None) or self.db
        names = _ANIM_NAMES.get(id(root))
        if names is None:
            names = _ANIM_NAMES[id(root)] = {k: v.lower() for k, v in animation_names(root).items()}
        file = self.cat.name(self.db.binary_ref(animation)) if animation is not None else None
        clip = file.rsplit("/", 1)[-1].split(".(")[0].rsplit(".", 1)[-1].lower() if file and "." in file.rsplit("/", 1)[-1].split(".(")[0] else "idle"
        return any(names.get(i) == clip for i in state_ids)

    def state_animation(self, off: int, clip: str) -> int | None:
        """Animation de l'état du gabarit dont le fichier porte le clip `clip` (`special01` →
        `IH1_Door_01.Special01.(SkeletalAnimation).bin`), sans égard à la casse."""
        wanted = f".{clip.lower()}.("
        for e in self.db.elements(off + VOT_STATES, STATE_STRIDE):
            anim = self.db.ptr(e + STATE_ANIMATION)
            name = self.cat.name(self.db.binary_ref(anim)) if anim is not None else None
            if name and wanted in name.lower():
                return anim
        return None

    def emit_state(self, off: int, clip: str) -> str | None:
        """Variante `<gabarit>@<clip>` d'un gabarit : son modèle, l'animation de l'état `clip`, jouée
        une fois puis tenue (`CLAMP` des états d'un dispositif : porte ouverte ou fermée)."""
        anim = self.state_animation(off, clip)
        if anim is None:
            return None
        name = f"{self.name_of(off)}@{clip}"
        if name not in self.meta:
            node = self.emit(off, animation=anim, variant=name)
            if node is None:
                return None
            self.roots.append(node)
            self.meta[name]["loop"] = False
        return name

    def emit(self, off: int, depth: int = 0, animation: int | None = None, variant: str | None = None) -> int | None:
        """Nœud d'un gabarit : géométrie skinnée animée, composants accrochés. `animation`,
        `variant` : autre animation (celle d'un état) sous un autre nom (`emit_state`)."""
        if depth > 8:
            return None
        vot = read_visobject(self.db, self.cat, off)
        if animation is not None:
            vot.animation = animation
        name = variant or self.name_of(off)
        ex = self.exporter
        children: list[int] = []
        joint_nodes: list[int] = []
        joint_names: list[str] = []
        locators: dict[str, tuple] = {}
        duration = 0.0
        loop = False
        info: dict = {"fadeIn": vot.fade_in_ms / 1000.0, "fadeOut": vot.fade_out_ms / 1000.0,
                      "scale": vot.scale}
        if vot.sound:
            info["sound"] = vot.sound
            self.sounds.add(vot.sound)
        if vot.particle is not None:
            system = self.particles.system(vot.particle, self.report) if self.particles else None
            if system is not None:
                info["particles"] = system
        loaded = load_geometry(self.db, self.cat, self.bins, vot.geometry) if vot.geometry is not None else None
        if loaded is not None:
            geo = loaded.geo
            if geo.orientation != "COMMON":
                info["orientation"] = geo.orientation
            for loc in geo.doc.locators:
                locators[loc.name] = loc
            # Un élément sans texture n'est pas dessiné (mêmes emplacements vides que les
            # armures des personnages ; ici les formes d'émission Maya — anneaux gris opaques
            # de `FatalityWarlock` — qui boucheraient la vue).
            elements = [e for e in geo.doc.elements if e.material.visible and e.material.texture]
            mesh, skinned = ex.emit_mesh(name, geo, loaded.vertices, loaded.indices, elements, loaded.skeleton)
            if mesh is not None:
                ex.stats["objects"] += 1
                mesh_node = {"name": f"{name}_mesh", "mesh": mesh}
                skeleton = loaded.skeleton
                anim_name = self.cat.name(self.db.binary_ref(vot.animation)) if vot.animation is not None else None
                span = float(np.max(np.abs(loaded.vertices["position"])) * 8.0) if len(loaded.vertices["position"]) else 0.0
                animation = load_animation(self.bins, anim_name, skeleton, span) if anim_name else None
                speed = (self.db.f32(vot.animation + 0x100) or 1.0) if animation is not None else 1.0
                looped = animation is not None and bool(self.db.u8(vot.animation + 0x108))
                if skeleton is not None and skinned:
                    joint_nodes = ex.emit_skeleton(skeleton, name)
                    joint_names = list(skeleton.names)
                    static_node = ex.gltf.add_node({"name": f"{name}/Static"})
                    mesh_node["skin"] = ex.skin(name, skeleton, joint_nodes, static_node)
                    children.extend(joint_nodes[i] for i in range(len(skeleton))
                                    if not (0 <= skeleton.parents[i] < len(skeleton)))
                    children.append(static_node)
                    if animation is not None:
                        loop = looped
                        duration = ex.emit_clip(name, skeleton, joint_nodes, animation, speed)
                if animation is not None:
                    alpha = element_alpha(animation, {e.name for e in elements}, speed)
                    if alpha:
                        info["elementAlpha"] = alpha
                        loop = looped
                        # Le clip porte au moins la transparence de ses éléments : sa durée
                        # compte même sans squelette animé (dague du Paladin, feux du Guerrier).
                        if duration <= 0 and animation.frames > 1:
                            duration = (animation.frames - 1) / float(animation.fps) / max(speed, 1e-6)
                children.append(ex.gltf.add_node(mesh_node))
        info["duration"] = round(duration, 4)
        info["loop"] = loop
        # Étendue du gabarit (boîte de son animation dans le client) : cadrage du lecteur.
        bounds = animation_bounds(self.db, vot.animation, vot.geometry) if loaded is not None else None
        if bounds is not None:
            info["bounds"] = bounds
        attached = []
        for comp in vot.components:
            if comp.visobject is None:
                continue
            if comp.state_ids is not None and not self.default_state(comp.state_ids, vot.animation):
                # `StateComponent` d'un autre état que celui du gabarit posé (son animation par défaut) :
                # rien ne le pilote dans le décor (les stèles posent les leurs, `stele_components`).
                self.exporter.notes.append(f"{name} : composant d'état {self.name_of(comp.visobject)} hors de l'état par défaut")
                continue
            if comp.cancelled:
                self.exporter.notes.append(f"{name} : composant {comp.ident} annulé (arrêté avant son échéance)")
                continue
            child = self.emit(comp.visobject, depth + 1)
            if child is None:
                continue
            node = ex.gltf.json["nodes"][child]
            t = np.array(comp.offset, float)
            r = comp.rotation
            # Échelle du composant × échelle propre du gabarit accroché (les racines, elles,
            # reçoivent la leur dans le lecteur).
            s = comp.scale * (read_visobject(self.db, self.cat, comp.visobject).scale or 1.0)
            if comp.locator in joint_names:
                ex.gltf.json["nodes"][joint_nodes[joint_names.index(comp.locator)]].setdefault("children", []).append(child)
            elif comp.locator in locators:
                loc = locators[comp.locator]
                t = np.array(loc.position) + _rotate(loc.rotation, t) * loc.scale
                r = _qmul(loc.rotation, r)
                s = s * loc.scale
                children.append(child)
            else:
                if comp.locator:
                    self.exporter.notes.append(f"{name} : locator {comp.locator} introuvable (composant à l'origine)")
                children.append(child)
            if np.any(np.abs(t) > 1e-9):
                node["translation"] = [float(v) for v in t]
            if abs(r[3] - 1) > 1e-9 or any(abs(v) > 1e-9 for v in r[:3]):
                node["rotation"] = [float(v) for v in r]
            if abs(s - 1) > 1e-9:
                node["scale"] = [float(s)] * 3
            if comp.start > 0 or comp.stop is not None:
                node.setdefault("extras", {})["window"] = [comp.start, comp.stop]
            item = {"vot": self.name_of(comp.visobject), "locator": comp.locator}
            if comp.start > 0:
                item["start"] = comp.start
            if comp.stop is not None:
                item["stop"] = comp.stop
            if comp.random_delay:
                self.exporter.notes.append(f"{name} : délai aléatoire de {item['vot']} pris à sa borne basse")
            attached.append(item)
        if attached:
            info["components"] = attached
        self.meta[name] = info
        return ex.gltf.add_node({"name": f"vot:{name}", "children": children, "extras": {"vot": name}})


#: Écart toléré sur l'opacité d'un élément entre deux clés gardées (un pas de l'octet source).
ALPHA_TOLERANCE = 1.0 / 255.0


def element_alpha(animation, drawn: set[str], speed: float = 1.0) -> dict[str, list[float]]:
    """Transparence des éléments dessinés, en clés `[t0, a0, t1, a1, …]` (secondes du clip à
    sa vitesse, opacité 0 à 1, interpolation linéaire) : seules les pistes qui ne sont pas
    pleines d'un bout à l'autre, allégées des clés redondantes."""
    out: dict[str, list[float]] = {}
    for track in animation.elements:
        alpha = track.alpha
        if alpha is None or track.name not in drawn or track.name in out or float(alpha.min()) >= 1.0:
            continue
        keep = reduce_keys(alpha[:, None], ALPHA_TOLERANCE)
        times = np.arange(len(alpha)) / float(animation.fps) / max(speed, 1e-6)
        out[track.name] = [round(float(v), 4) for k in keep for v in (times[k], alpha[k])]
    return out


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return np.array((vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx)))


# --- particules --------------------------------------------------------------------------------

class ParticlePool:
    """Systèmes de particules exportés : binaire du client allégé (`allods_particles.simplify`,
    même format) compressé en zlib dans `particles/`, et un atlas réduit aux seules images
    utilisées (découpées dans `Client/Render/ParticleAtlas`)."""

    def __init__(self, db: PackDB, cat: PakCatalog, bins: BinSource, out_dir: Path) -> None:
        self.db, self.cat, self.bins = db, cat, bins
        self.dir = out_dir / "particles"
        self.systems: dict[str, dict] = {}
        self.rects: list[tuple[str, int, int, int, int]] = []
        self.rect_index: dict[tuple, int] = {}
        self.bytes_written = 0
        # Largeur de l'atlas réduit (`PARTICLE_ATLAS_WIDTH` ; 2048 pour les auras, riches en textures entières).
        self.width = PARTICLE_ATLAS_WIDTH

    def system(self, off: int, report: list[str]) -> dict | None:
        from tools.allods_particles import encode_particles, parse_particles, simplify
        from tools.allods_visdb import atlas_rect, read_particle_animation
        info = read_particle_animation(self.db, self.cat, off)
        if not info.binary:
            return None
        if info.binary in self.systems:
            return self.systems[info.binary]
        data = self.bins.get(info.binary)
        payload = read_chunks(data).get(0) if data else None
        if not payload:
            report.append(f"AVERTISSEMENT : particules absentes {info.binary}")
            self.systems[info.binary] = None
            return None
        pf = parse_particles(payload)
        if len(pf.emitters) != len(info.emitters):
            report.append(f"AVERTISSEMENT : {info.binary} : {len(pf.emitters)} émetteurs dans le binaire, "
                          f"{len(info.emitters)} dans la ressource")
        packed = zlib.compress(encode_particles(simplify(pf)), 9)
        file = re.sub(r"\.\(ParticleAnimation\)\.bin$", "", info.binary.split("/")[-1]) + ".bin"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / file).write_bytes(packed)
        self.bytes_written += len(packed)
        frames = []
        own = own_textures(self.db, off)
        for k, element in enumerate(info.textures):
            rect = atlas_rect(self.db, self.cat, element)
            if rect is None and element is None and k < len(own) and own[k] is not None:
                # Image propre au système (texture entière, hors de `Client/Render/ParticleAtlas`) :
                # runes et cercles des auras, dont l'élément d'atlas est nul. Rangée dans l'atlas
                # réduit, au plus `WHOLE_TEXTURE_MAX`.
                rect = whole_texture_rect(self.db, self.cat, own[k])
            if rect is None:
                frames.append(-1)
                continue
            if rect not in self.rect_index:
                self.rect_index[rect] = len(self.rects)
                self.rects.append(rect)
            frames.append(self.rect_index[rect])
        entry = {
            "file": f"particles/{file}", "speed": info.speed, "loop": info.looped,
            "endFrame": info.end_frame, "loopFrame": info.loop_frame, "frames": frames,
            "emitters": [{"additive": e.additive, "tint": [round(c / 128.0, 4) for c in e.color[:3]],
                          "render": e.render, "pivot": [round(v, 4) for v in e.pivot],
                          "virtualOffset": round(e.virtual_offset, 4), "looping": e.looping,
                          "worldSpace": e.world_space, "flip": list(e.flip),
                          **({"decal": True} if e.decal else {})} for e in info.emitters],
        }
        self.systems[info.binary] = entry
        return entry

    def write_atlas(self, textures: "TexturePool") -> dict | None:
        """Assemble les images utilisées en rangées (plus haute d'abord) dans un atlas carré."""
        if not self.rects:
            return None
        sources: dict[str, Image.Image] = {}
        for name, *_ in self.rects:
            if name and name not in sources:
                img = textures.image(name.removesuffix(WHOLE_SUFFIX), 4096)
                if img is not None:
                    sources[name] = img
        order = sorted(range(len(self.rects)), key=lambda i: -self.rects[i][4])
        width = self.width
        x = y = row = 0
        placed: dict[int, tuple[int, int]] = {}
        for i in order:
            _, _, _, w, h = self.rects[i]
            if x + w > width:
                x, y, row = 0, y + row, 0
            placed[i] = (x, y)
            x += w
            row = max(row, h)
        height = 1
        while height < y + row:
            height *= 2
        atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        out_rects = []
        for i, (name, sx, sy, w, h) in enumerate(self.rects):
            src = sources.get(name)
            px, py = placed[i]
            if src is not None and name.endswith(WHOLE_SUFFIX):
                atlas.paste(src if src.size == (w, h) else src.resize((w, h), Image.LANCZOS), (px, py))
            elif src is not None:
                atlas.paste(src.crop((sx, sy, sx + w, sy + h)), (px, py))
            out_rects.append([px, py, w, h])
        self.dir.mkdir(parents=True, exist_ok=True)
        atlas.save(self.dir / "atlas.png", format="PNG", optimize=True)
        self.bytes_written += (self.dir / "atlas.png").stat().st_size
        return {"file": "particles/atlas.png", "width": width, "height": height, "rects": out_rects,
                "sources": [list(r) for r in self.rects]}

    def seed(self, previous: dict | None) -> None:
        """Reprend les images de l'atlas précédent, dans le même ordre : un export partiel
        (`--only-fx`) garde valables les indices des fatalités qu'il ne réécrit pas."""
        for rect in (previous or {}).get("sources", []):
            key = tuple(rect)
            if key not in self.rect_index:
                self.rect_index[key] = len(self.rects)
                self.rects.append(key)


# Largeur de l'atlas réduit (les images de l'atlas du client font 32 à 256 px).
PARTICLE_ATLAS_WIDTH = 1024
# Texture entière d'un système de particules (pas un élément de `ParticleAtlas`) : marquée par ce
# suffixe dans l'atlas réduit, ramenée à `WHOLE_TEXTURE_MAX` px au plus (les runes des auras
# montent à 1024 px pour des particules d'1 à 3 m).
WHOLE_SUFFIX = "#whole"
WHOLE_TEXTURE_MAX = 256


#: Vecteur des textures propres d'un `ParticleAnimation` (pointeurs `Texture`, un par image, en
#: regard des éléments d'atlas de `PART_TEXTURES` ; relevé sur `HeroesArena_Aura02` du 17.0 :
#: élément d'atlas nul, texture `HeroesArena_Aura02` ici).
PART_OWN_TEXTURES = 0xE0


def own_textures(db: PackDB, off: int) -> list[int | None]:
    v = db.vec(off + PART_OWN_TEXTURES)
    if not v:
        return []
    out = []
    for k in range(v[1] // 8):
        p = db.ptr(v[0] + 8 * k)
        out.append(p if p is not None and db.vtype(p) == "Texture" else None)
    return out


def whole_texture_rect(db: PackDB, cat: PakCatalog, texture: int) -> tuple[str, int, int, int, int] | None:
    """Entrée d'atlas d'une texture entière : `(nom#whole, 0, 0, largeur, hauteur)`, réduite de
    moitié en moitié (niveaux de mipmap) jusqu'à tenir dans `WHOLE_TEXTURE_MAX`."""
    from tools.allods_visdb import read_texture
    info = read_texture(db, cat, texture)
    if not info.binary or not info.width or not info.height:
        return None
    w, h = info.width, info.height
    while max(w, h) > WHOLE_TEXTURE_MAX and min(w, h) > 1:
        w, h = w // 2, h // 2
    return (info.binary + WHOLE_SUFFIX, 0, 0, w, h)



# --- sons --------------------------------------------------------------------------------------

# Banques des fatalités, puis celles des deux effets empruntés à d'autres sorts (gel du Mage :
# `Mobs/WormGracial/FrozenStatue`, dans `WormGracialSpells` ; lance de Smeyana :
# `SmeyanaFX/spearFireHit`, dans `Spells_FX2`), fouillées seulement pour les ondes manquantes.
SOUND_BANKS = ("SFX/Spells/Fatality.bsb", "SFX/Spells/Fatality2.bsb", "SFX/Spells/WormGracialSpells.bsb",
               "SFX/Spells/Spells_FX2.bsb")


def _sound_key(name: str) -> str:
    """Clé d'appariement événement ↔ onde : casse et soulignés ignorés (l'événement
    `FatalityUniversal` joue l'onde `fatality_universal.wav`, seul écart de nommage des banques
    de fatalités)."""
    return name.lower().replace("_", "")


def export_sounds(names: set[str], bins: BinSource, out_dir: Path, vgmstream: Path, report: list[str],
                  banks: tuple[str, ...] = SOUND_BANKS) -> dict[str, str]:
    """Événement FMOD → onde. Les événements des fatalités (`spells/FX/Spells/Fatality/X`)
    n'ont qu'une onde, `fx/spells/fatality/X.wav` dans `Sounds.bev`, rangée sous le nom `X`
    dans les banques `Fatality*.bsb` : on apparie par ce nom."""
    from tools.extract_audio import encode_outputs, fsb_payload_from_bytes, run_vgmstream
    import subprocess
    wanted = {_sound_key(n.split("/")[-1]): n for n in names}
    found: dict[str, str] = {}
    target = out_dir / "sfx"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for bank in banks:
            if len(found) == len(wanted):
                break
            data = bins.get(bank)
            payload = fsb_payload_from_bytes(data, bank) if data else None
            if payload is None:
                report.append(f"AVERTISSEMENT : banque absente {bank}")
                continue
            fsb = Path(tmp) / (Path(bank).stem + ".fsb")
            fsb.write_bytes(payload)
            listing = subprocess.run([str(vgmstream), "-m", str(fsb)], capture_output=True, text=True).stdout
            m = re.search(r"stream count: (\d+)", listing)
            count = int(m.group(1)) if m else 1
            for sub in range(1, count + 1):
                info = subprocess.run([str(vgmstream), "-m", "-s", str(sub), str(fsb)], capture_output=True, text=True).stdout
                sm = re.search(r"stream name: (.*)", info)
                stream = sm.group(1).strip() if sm else ""
                key = _sound_key(stream)
                if key not in wanted or key in found:
                    continue
                stream_file = stream
                base = target / stream_file
                if not (base.with_suffix(".ogg").exists() and base.with_suffix(".mp3").exists()):
                    wav = Path(tmp) / f"{stream_file}.wav"
                    run_vgmstream(vgmstream, fsb, sub, wav)
                    encode_outputs(wav, base, "sfx")
                found[key] = f"sfx/{stream_file}"
    for short, full in wanted.items():
        if short not in found:
            report.append(f"AVERTISSEMENT : onde introuvable pour l'événement {full}")
    return {wanted[k]: v for k, v in found.items()}



def fsb5_stream_names(payload: bytes) -> list[str]:
    """Noms des sous-pistes d'une banque FSB5 (table de noms après les entêtes d'échantillons),
    dans l'ordre des sous-pistes de vgmstream (1 = premier nom)."""
    if payload[:4] != b"FSB5":
        return []
    version, count, headers, names_size = struct.unpack_from("<4I", payload, 4)
    if not names_size:
        return []
    base = (0x3C if version == 1 else 0x40) + headers
    offsets = struct.unpack_from(f"<{count}I", payload, base)
    return [payload[base + o:payload.index(b"\0", base + o)].decode("latin1") for o in offsets]
