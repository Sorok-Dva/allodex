"""Systèmes de particules du client (`(ParticleAnimation).bin`) : format et décodage.

Les particules du jeu sont **précalculées** (exportées de Maya image par image) : le binaire
donne, pour chaque émetteur, la liste de ses particules avec leur image de naissance et leurs
courbes clés. Format établi sur les données (septembre 2026, `FatalityWarrior_Fire`,
`FatalityWarrior_Bottom`, `Fatality_Cast`…) :

* entête `u32 nb_textures, u32 8, u32 nb_emetteurs` ;
* par émetteur, 48 octets : `f32 pos_min[3], f32 pos_pas[3], f32 taille_min[2],
  f32 taille_pas[2], u32 pointeur auto-relatif (vers sa table), u32 nb_particules` ;
* table de particules, 12 octets par particule : `u16 naissance (image), u16 N (intervalles
  de la grille de clés = durée de vie en images), u32 pointeur auto-relatif (vers ses
  données), u32 taille des données` ;
* données d'une particule : cinq canaux **dans cet ordre** — position (3 × u16), taille
  (2 × u16), rotation (1 × u16), couleur (4 × u8, R G B A), image de texture (1 × u8). Chaque
  canal : `nombre de clés c`, puis les `c − 2` positions intermédiaires sur la grille `0..N`
  (la première, 0, et la dernière, N, sont implicites), puis `c` valeurs. Nombre et positions
  sont des `u8`, ou des `u16` dès que `N` dépasse 254 (particules persistantes).

Valeurs : position = `pos_min + v · pos_pas` (repère de l'émetteur), taille idem ; rotation
= `v / 65536` tour ; couleur multipliée par la teinte de l'émetteur (`Color`, 0x80 = neutre,
comme les couleurs de sommets) ; l'image de texture indexe la liste `textures` de la
ressource `ParticleAnimation` (éléments de l'atlas `Client/Render/ParticleAtlas`).
Temps : une image de grille = une image de l'animation (30 par seconde), vitesse `speed`.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

EMITTER_RECORD = 48
PARTICLE_RECORD = 12
# (nombre de composantes, octets par composante) des cinq canaux, dans l'ordre du fichier.
CHANNELS = (("position", 3, 2), ("size", 2, 2), ("rotation", 1, 2), ("color", 4, 1), ("frame", 1, 1))
WIDE_GRID = 254


@dataclass
class Channel:
    grid: np.ndarray        # positions des clés sur la grille 0..N (entiers croissants)
    values: np.ndarray      # (c, composantes) valeurs brutes


@dataclass
class Particle:
    birth: int
    span: int               # N : durée de vie en images
    channels: dict[str, Channel]


@dataclass
class Emitter:
    pos_min: np.ndarray
    pos_step: np.ndarray
    size_min: np.ndarray
    size_step: np.ndarray
    particles: list[Particle] = field(default_factory=list)


@dataclass
class ParticleFile:
    textures: int
    version: int
    emitters: list[Emitter]


def _channel(data: bytes, off: int, span: int, comps: int, width: int) -> tuple[Channel, int]:
    wide = span > WIDE_GRID
    fmt, size = ("<H", 2) if wide else ("<B", 1)
    count = struct.unpack_from(fmt, data, off)[0]
    off += size
    inner = max(0, count - 2)
    grid = list(struct.unpack_from(f"<{inner}{'H' if wide else 'B'}", data, off)) if inner else []
    off += inner * size
    if count >= 2:
        grid = [0] + grid + [span]
    else:
        grid = [0] * count
    dtype = "<u2" if width == 2 else "u1"
    values = np.frombuffer(data, dtype=dtype, count=count * comps, offset=off).reshape(count, comps)
    off += count * comps * width
    return Channel(np.array(grid, np.int32), values.astype(np.float64)), off


def parse_particles(data: bytes) -> ParticleFile:
    textures, version, count = struct.unpack_from("<3I", data, 0)
    emitters: list[Emitter] = []
    for i in range(count):
        rec = 12 + EMITTER_RECORD * i
        floats = np.array(struct.unpack_from("<10f", data, rec))
        rel, n = struct.unpack_from("<2I", data, rec + 40)
        table = rec + 40 + rel
        emitter = Emitter(floats[0:3], floats[3:6], floats[6:8], floats[8:10])
        for j in range(n):
            entry = table + PARTICLE_RECORD * j
            birth, span, prel, size = struct.unpack_from("<HHII", data, entry)
            off = entry + 4 + prel
            end = off + size
            channels = {}
            for name, comps, width in CHANNELS:
                channels[name], off = _channel(data, off, span, comps, width)
            if off > end:
                raise ValueError(f"particule {j} de l'émetteur {i} déborde ({off} > {end})")
            emitter.particles.append(Particle(birth, span, channels))
        emitters.append(emitter)
    return ParticleFile(textures, version, emitters)


# Écart toléré (en unités brutes) en retirant une clé de particule : ~0,15 % de la plage pour
# les positions et tailles, ~0,1 % de tour pour la rotation, 3/255 pour la couleur. L'image de
# texture (valeurs discrètes) garde toutes ses clés.
SIMPLIFY_TOLERANCE = {"position": 96.0, "size": 96.0, "rotation": 64.0, "color": 3.0, "frame": -1.0}


def simplify_channel(channel: Channel, tolerance: float) -> Channel:
    """Retire les clés que l'interpolation linéaire de leurs voisines restitue à `tolerance`
    près (même format : les positions gardées restent sur la grille d'origine)."""
    grid, values = channel.grid, channel.values
    n = len(grid)
    if tolerance < 0 or n <= 2:
        return channel
    keep = [0]
    anchor = 0
    for i in range(2, n):
        span = np.arange(anchor + 1, i)
        w = ((grid[span] - grid[anchor]) / max(grid[i] - grid[anchor], 1))[:, None]
        interp = values[anchor] * (1 - w) + values[i] * w
        if np.max(np.abs(interp - values[span])) > tolerance:
            keep.append(i - 1)
            anchor = i - 1
    keep.append(n - 1)
    return Channel(grid[keep], values[keep])


def simplify(pf: ParticleFile) -> ParticleFile:
    for emitter in pf.emitters:
        for particle in emitter.particles:
            for name in particle.channels:
                particle.channels[name] = simplify_channel(particle.channels[name], SIMPLIFY_TOLERANCE[name])
    return pf


def encode_particles(pf: ParticleFile) -> bytes:
    """Réécrit un fichier au format du client (entête, émetteurs, tables, canaux)."""
    header = struct.pack("<3I", pf.textures, pf.version, len(pf.emitters))
    records_size = EMITTER_RECORD * len(pf.emitters)
    blobs: list[tuple[bytes, list[bytes]]] = []
    for emitter in pf.emitters:
        datas = []
        for particle in emitter.particles:
            wide = particle.span > WIDE_GRID
            fmt = "H" if wide else "B"
            out = bytearray()
            for name, comps, width in CHANNELS:
                ch = particle.channels[name]
                count = len(ch.values)
                out += struct.pack("<" + fmt, count)
                inner = [int(g) for g in ch.grid[1:-1]] if count >= 2 else []
                out += struct.pack(f"<{len(inner)}{fmt}", *inner)
                dtype = "<u2" if width == 2 else "u1"
                out += np.round(ch.values).clip(0, 65535 if width == 2 else 255).astype(dtype).tobytes()
            while len(out) % 4:
                out.append(0)
            datas.append(bytes(out))
        blobs.append((b"", datas))
    # Disposition : entête, enregistrements d'émetteurs, puis pour chaque émetteur sa table
    # suivie des données de ses particules.
    body = bytearray()
    tables_at: list[int] = []
    base = len(header) + records_size
    for (_, datas), emitter in zip(blobs, pf.emitters):
        table_at = base + len(body)
        tables_at.append(table_at)
        table = bytearray()
        data_at = table_at + PARTICLE_RECORD * len(datas)
        cursor = data_at
        for j, (particle, data) in enumerate(zip(emitter.particles, datas)):
            entry = table_at + PARTICLE_RECORD * j
            table += struct.pack("<HHII", particle.birth, particle.span, cursor - (entry + 4), len(data))
            cursor += len(data)
        body += table
        for data in datas:
            body += data
    records = bytearray()
    for i, emitter in enumerate(pf.emitters):
        rec = len(header) + EMITTER_RECORD * i
        floats = np.concatenate([emitter.pos_min, emitter.pos_step, emitter.size_min, emitter.size_step]).astype("<f4")
        records += floats.tobytes() + struct.pack("<2I", tables_at[i] - (rec + 40), len(emitter.particles))
    return header + bytes(records) + bytes(body)


def sample(channel: Channel, x: float) -> np.ndarray:
    """Valeur interpolée linéairement à la position `x` de la grille (bornée)."""
    grid, values = channel.grid, channel.values
    if len(grid) == 1:
        return values[0]
    x = min(max(x, grid[0]), grid[-1])
    k = int(np.searchsorted(grid, x, side="right") - 1)
    k = min(max(k, 0), len(grid) - 2)
    span = grid[k + 1] - grid[k]
    w = 0.0 if span <= 0 else (x - grid[k]) / span
    return values[k] * (1 - w) + values[k + 1] * w
