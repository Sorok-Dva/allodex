"""Fichiers d'événements FMOD du client (`SFX/**/*.bev`) : quel événement joue quelle onde.

Un `.bev` est un projet FMOD Designer 4.44 compilé (`.fev`), compressé en zlib et précédé d'un
entête de 68 octets propre au jeu. Format lu (recoupé sur `Music.bev`, `Ambience.bev`,
`Ships.bev`, `World.bev` et les noms des sous-pistes des banques FSB5) :

- `RIFF` `FEV ` : `FMT ` (version `0x00450000`), `LIST` `PROJ` avec `LGCY` (le contenu de
  l'ancien format `FEV1`) et `STRR` (table des noms : `u32` nombre, `u32` décalages, chaînes) ;
- `LGCY` : `u32`, `u32`, nom du projet (chaîne longueur + texte), `u32` nombre de banques,
  `u32`, puis par banque `u32` mode, `u32` flux, 8 octets, `u32`, nom ; l'indice de banque des ondes compte
  à partir de la première banque ;
- événement : `u32` type (8 complexe, 16 simple), `u32` nom (indice `STRR`), GUID, `f32`
  volume… ; à `+0xA8`, un événement simple porte `u32` 1 et `u32` l'indice de sa définition de
  son ; un complexe, ses calques (`u32` nombre) : `u16` drapeaux, `i16` priorité, `i16`
  paramètre (−1 : aucun), `u16` sons, `u16` enveloppes ; un son (58 octets) commence par
  l'indice `u16` de sa définition, finit par les fondus (`f32` −1, −1, `u32` 2, 2) ;
- définitions de sons (la table dont le premier nom est le premier chemin `/…` de `STRR`) :
  `u32` nombre, puis par définition `u32` nom, `u32` réglage, `u32` ondes, et par onde `u32`
  type (0 : onde d'une banque, 2 : silence), `u32` poids ; une onde de banque porte le nom de
  son fichier source, `u32` banque, `u32` indice dans la banque (sous-piste FSB, depuis 0),
  `u32` durée en ms.

Les sons d'un événement sont retrouvés dans l'étendue de son enregistrement (jusqu'à
l'événement suivant) par leur signature ; les enveloppes (courbes pilotées par un paramètre
du jeu : musiques adaptatives, distance) ne sont pas interprétées.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

_INSTANCE_TAIL = struct.pack("<ffII", -1.0, -1.0, 2, 2)


@dataclass
class Wave:
    file: str          # fichier source (`adaptivemusic/Conquer_high.wav`), nom de la sous-piste
    bank: str          # nom de la banque (`Music_StartZones`)
    index: int         # sous-piste dans la banque, depuis 0
    ms: int
    weight: int

    @property
    def stream(self) -> str:
        return self.file.rsplit("/", 1)[-1].rsplit(".", 1)[0]


@dataclass
class SoundDef:
    name: str
    waves: list[Wave]


@dataclass
class Event:
    name: str
    offset: int
    layers: list[tuple[int, list[int]]] = field(default_factory=list)   # (paramètre, définitions)


@dataclass
class Project:
    name: str
    banks: list[str]
    sounddefs: list[SoundDef]
    events: list[Event]

    def find(self, name: str) -> list[Event]:
        return [e for e in self.events if e.name.lower() == name.lower()]


def _strings(body: bytes) -> list[str]:
    n = struct.unpack_from("<I", body, 0)[0]
    offs = struct.unpack_from(f"<{n}I", body, 4)
    base = 4 + 4 * n
    return [body[base + o:body.index(b"\0", base + o)].decode("latin1") for o in offs]


def _chunks(d: bytes, off: int, end: int, out: dict):
    while off + 8 <= end:
        tag = d[off:off + 4]
        size = struct.unpack_from("<I", d, off + 4)[0]
        if tag in (b"RIFF", b"LIST"):
            _chunks(d, off + 12, off + 8 + size, out)
        else:
            out[tag.decode("latin1")] = (off + 8, off + 8 + size)
        off += 8 + size + (size & 1)


def _cstr(d: bytes, p: int) -> tuple[str, int]:
    n = struct.unpack_from("<I", d, p)[0]
    return d[p + 4:p + 4 + max(0, n - 1)].decode("latin1"), p + 4 + n


def _sounddefs(d: bytes, start: int, end: int, strs: list[str], banks: list[str]) -> list[SoundDef]:
    """Table des définitions : un nombre suivi d'enregistrements tous nommés d'un chemin `/…`
    (le premier est le premier chemin de `STRR`) ; la plus longue qui se lit en entier."""
    first = min(i for i, s in enumerate(strs) if s.startswith("/"))
    best: list[SoundDef] = []
    for at in range(start, end - 8):
        n, name = struct.unpack_from("<II", d, at)
        if name != first or not len(best) < n < 100000:
            continue
        p, out = at + 4, []
        try:
            for _ in range(n):
                name, _cfg, nw = struct.unpack_from("<III", d, p)
                if not strs[name].startswith("/"):
                    raise ValueError("nom")
                p += 12
                waves = []
                for _ in range(nw):
                    typ, weight = struct.unpack_from("<II", d, p)
                    p += 8
                    if typ == 0:
                        file, p = _cstr(d, p)
                        bank, index, ms = struct.unpack_from("<III", d, p)
                        p += 12
                        waves.append(Wave(file, banks[bank], index, ms, weight))
                    elif typ != 2:
                        raise ValueError(f"onde de type {typ}")
                out.append(SoundDef(strs[name], waves))
        except (ValueError, IndexError, struct.error):
            continue
        best = out
    return best


def parse_bev(raw: bytes) -> Project:
    try:
        raw = zlib.decompress(raw)
    except zlib.error:
        pass
    at = raw.find(b"RIFF")
    chunks: dict = {}
    _chunks(raw, at, len(raw), chunks)
    lo, hi = chunks["LGCY"]
    s0, s1 = chunks["STRR"]
    strs = _strings(raw[s0:s1])
    name, p = _cstr(raw, lo + 8)
    nbanks = struct.unpack_from("<I", raw, p)[0]
    p += 8
    banks = []
    for _ in range(nbanks):
        bank, p = _cstr(raw, p + 20)
        banks.append(bank)
    sdefs = _sounddefs(raw, p, hi, strs, banks)
    # événements : entête (type 8 complexe ou 16 simple, nom, GUID, volume)
    heads = []
    for i in range(p, hi - 0xB0):
        t, n = struct.unpack_from("<II", raw, i)
        if t in (8, 16) and 0 < n < len(strs) and not strs[n].startswith("/"):
            vol = struct.unpack_from("<f", raw, i + 24)[0]
            if 0 < vol <= 1.0 and raw[i + 8:i + 24].count(0) < 6:
                heads.append((i, t, strs[n]))
    events = []
    for (i, kind, ename), nxt in zip(heads, heads[1:] + [(hi, 0, "")]):
        ev = Event(ename, i)
        q = i + 0xA8
        nlayers, simple = struct.unpack_from("<II", raw, q)
        if kind == 16:
            # événement simple : `u32` 1, `u32` définition de son
            if nlayers == 1 and simple < len(sdefs):
                ev.layers.append((-1, [simple]))
            events.append(ev)
            continue
        if nlayers > 64:
            continue
        # calques et sons par signature, dans l'étendue de l'événement
        layer_param = None
        k = q + 4
        while k < nxt[0] - 10:
            fl, _pr, par, ni, ne = struct.unpack_from("<HhhHH", raw, k)
            sd = struct.unpack_from("<H", raw, k + 10)[0]
            if ni and ni < 64 and ne < 64 and sd < len(sdefs) and raw[k + 10 + 42:k + 10 + 58] == _INSTANCE_TAIL:
                layer_param = par
                defs = []
                for j in range(ni):
                    base = k + 10 + j * 58
                    if raw[base + 42:base + 58] != _INSTANCE_TAIL:
                        break
                    defs.append(struct.unpack_from("<H", raw, base)[0])
                ev.layers.append((layer_param, defs))
                k += 10 + 58 * len(defs)
                continue
            k += 1
        events.append(ev)
    return Project(name, banks, sdefs, events)


def event_waves(project: Project, event: str) -> tuple[list[tuple[int, Wave]], str | None]:
    """Ondes jouées par un événement (`Music/ZonesMusic/IE1_main`, projet en tête) : liste de
    (paramètre du calque, onde), première onde de chaque définition (une définition à plusieurs
    ondes en tire une au hasard). Deuxième valeur : raison d'un échec (nom ambigu, silence)."""
    tail = event.split("/")[-1]
    hits = project.find(tail)
    if not hits:
        return [], "événement absent"
    if len(hits) > 1:
        return [], f"nom ambigu ({len(hits)} événements)"
    out = []
    for param, defs in hits[0].layers:
        for sd in defs:
            waves = project.sounddefs[sd].waves
            if waves:
                out.append((param, waves[0]))
    return out, None if out else "aucune onde (silence)"


class FevResolver:
    """Ondes des événements par les `.bev` des paks : projet = premier segment de l'événement
    (`Music/ZonesMusic/IE1_main` → `SFX/**/Music.bev`), banque = fichier `<banque>.fsb|bsb` du
    même dossier de préférence ; la sous-piste n'est retenue que si son nom dans la banque FSB
    est celui de l'onde (quelques définitions pointent des ondes retirées des banques)."""

    def __init__(self, names, get, streams_of):
        self._names = list(names)      # chemins des paks
        self._get = get                # chemin → octets
        self._streams_of = streams_of  # chemin de banque → noms des sous-pistes (0 = première)
        self._projects: dict = {}

    def project(self, name: str):
        key = name.lower()
        if key not in self._projects:
            paths = sorted((n for n in self._names if n.lower().endswith(".bev")
                            and n.rsplit("/", 1)[-1][:-4].lower() == key), key=lambda n: ("english" in n.lower(), n))
            self._projects[key] = (paths[0], parse_bev(self._get(paths[0]))) if paths else None
        return self._projects[key]

    def bank_path(self, bank: str, near: str) -> str | None:
        folder = near.rsplit("/", 1)[0].lower()
        hits = [n for n in self._names if n.lower().endswith((".fsb", ".bsb"))
                and n.rsplit("/", 1)[-1][:-4].lower() == bank.lower()]
        hits.sort(key=lambda n: (n.rsplit("/", 1)[0].lower() != folder, n))
        return hits[0] if hits else None

    def waves(self, event: str) -> tuple[list[dict], str | None]:
        """Ondes vérifiées d'un événement : `bank` (chemin du pak), `sub` (sous-piste vgmstream,
        depuis 1), `stream`, `param` (paramètre du calque, −1 : aucun), `bev`, `file`."""
        found = self.project(event.split("/")[0])
        if found is None:
            return [], "pas de fichier .bev pour ce projet"
        path, project = found
        waves, reason = event_waves(project, event)
        out = []
        for param, wave in waves:
            bank = self.bank_path(wave.bank, path)
            names = self._streams_of(bank) if bank else []
            if wave.index >= len(names) or names[wave.index].lower() != wave.stream.lower():
                reason = f"onde {wave.stream} absente de la banque {wave.bank} (sous-piste {wave.index + 1})"
                continue
            out.append({"bank": bank, "sub": wave.index + 1, "stream": names[wave.index], "param": param,
                        "bev": path, "file": wave.file})
        return out, (None if out else reason)
