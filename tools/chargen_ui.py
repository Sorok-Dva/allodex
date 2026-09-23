"""Interface de la création de personnage : arbre de widgets de l'addon `CharacterGenerator`.

Adapté de `UiExtractor` (`tools/extract_talents.py`, branche des talents, agent a98cc40e, non
fusionnée) et porté sur `tools/allods_packdb.py`. Décalages des champs `client.Widgets.*` du
`pack.bin` 64 bits (vérifiés sur l'addon des talents contre les `.xdb` 7.0, et ici sur
`FactionsPanel/Part01` : 433 × 736, calée en bas à gauche, texture 512 × 1024 utile 433 × 736) :

* `Widget` : calque de fond `+0x28`, enfants `+0x30`, nom `+0x58`, placement X `+0x78` et Y
  `+0x98` (`align` u32, `highPos` f32 +4, `pos` f32 +0x10, `size` f32 +0x14), priorité `+0xE8` ;
* `WidgetButton` : balise de texte `+0x120`, variantes `+0x1C0` (pas 0x188), chacune portant les
  calques de ses états ; l'état (normal, survolé, appuyé, désactivé…) se lit dans le nom de la
  texture (`ButtonAcceptPressedHighlighted`) ;
* `WidgetLayer*` : mélange `+0x24` (0 alpha, 2 additif), couleur ARGB `+0x28`, `UISingleTexture` → `UITexture` ;
* `UITexture` : indice du pak (bloc 6 du `pack.bin`) `+0x40`, rang dans le pak `+0x48`, hauteur
  `+0x78`, hauteur utile `+0x88`, largeur utile `+0x8C`, format `+0x90`, largeur `+0x94`.
"""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path

from tools.allods_packdb import BLOCK_RELOCATIONS, PackDB
from tools.uitexture import decode_uitexture, trim_transparent_padding

W_BACK = 0x28
W_CHILDREN = 0x30
W_NAME = 0x58
W_X = 0x78
W_Y = 0x98
W_PRIORITY = 0xE8
B_TEXTTAG = 0x120
B_VARIANTS = 0x1C0
B_VARIANT_STRIDE = 0x188
L_COLOR = 0x28
L_BLEND = 0x24     # 0 alpha ; 2 additif (lueurs de survol des factions, noir = transparent)
ALIGN = ["low", "high", "center", "both", "lowAbs"]
STATES = ("PressedHighlighted", "Highlighted", "Pressed", "Disabled", "Selected", "Normal", "Highlight",
          "Current", "Expects", "Finished", "Over")


def pak_names(db: PackDB) -> list[str]:
    """Noms des paks (bloc 6, UTF-16) que désignent les `UITexture` par leur indice."""
    raw = db.raw
    off, count = db.data + db.data_size, None
    # le bloc de relocations suit les données
    kind, count = struct.unpack_from("<IQ", raw, off)
    assert kind == BLOCK_RELOCATIONS
    off += 12 + 16 * count
    names: list[str] = []
    while off + 12 <= len(raw):
        kind, n = struct.unpack_from("<IQ", raw, off)
        off += 12
        if kind == 5:
            off += 8 * n
            continue
        if kind == 6:
            for _ in range(n):
                ln = struct.unpack_from("<Q", raw, off)[0]
                names.append(bytes(raw[off + 8:off + 8 + ln]).decode("utf-16-le", "replace"))
                off += 8 + ln
        break
    return names


class UiExtractor:
    def __init__(self, db: PackDB, packs_dir: Path, out_dir: Path) -> None:
        self.db = db
        self.packs_dir = Path(packs_dir)
        self.out = Path(out_dir)
        self.paks = pak_names(db)
        self.textures: dict[str, dict] = {}
        self._zips: dict[str, zipfile.ZipFile] = {}

    # -- utilitaires

    def ptrs(self, a: int, b: int) -> list[tuple[int, int]]:
        return [(loc, t) for loc, kind, t in self.db.relocs(a, b) if kind == 0]

    def zip(self, pak: str) -> zipfile.ZipFile:
        if pak not in self._zips:
            self._zips[pak] = zipfile.ZipFile(self.packs_dir / pak)
        return self._zips[pak]

    def ui_texture(self, tex: int) -> str | None:
        db = self.db
        pak_i, entry = db.u32(tex + 0x40), db.u32(tex + 0x48)
        if pak_i >= len(self.paks):
            return None
        pak = self.paks[pak_i]
        z = self.zip(pak)
        info = z.infolist()[entry]
        path = info.filename.replace("\\", "/")
        key = re.sub(r"\.\(UITexture\)\.bin$", "", path.split("/")[-1])
        folder = path.split("/")[-2] if "/" in path else ""
        if key in self.textures and self.textures[key]["path"] != path:
            key = f"{folder}_{key}"
        if key in self.textures:
            return key
        w, h = db.u32(tex + 0x94), db.u32(tex + 0x78)
        rw, rh = db.u32(tex + 0x8C), db.u32(tex + 0x88)
        data = z.read(info)
        try:
            img, _ = decode_uitexture(data, (w, h) if w and h else None)
        except ValueError:
            img, _ = decode_uitexture(data)
        if rw and rh:
            img = img.crop((0, 0, min(rw, img.width), min(rh, img.height)))
        self.out.mkdir(parents=True, exist_ok=True)
        img.save(self.out / f"{key}.png", optimize=True)
        self.textures[key] = {"path": path, "file": f"{key}.png", "width": img.width, "height": img.height}
        return key

    def single(self, a: int | None) -> str | None:
        if a is None or self.db.vtype(a) != "UISingleTexture":
            return None
        # Les références « par identifiant » (genre 2) ne sont pas suivies : leur cible n'a pas
        # toujours le type attendu (voir `tools/packbin.py`) ; `related_textures` les retrouve
        # par leur nom de fichier.
        for _, t in self.ptrs(a, a + 0x38):
            if self.db.vtype(t) == "UITexture":
                return self.ui_texture(t)
        return None

    def layer(self, a: int | None) -> dict | None:
        ty = self.db.vtype(a) if a is not None else None
        if not ty or not ty.startswith("WidgetLayer"):
            return None
        out: dict = {"type": ty.replace("WidgetLayer", ""), "color": f"{self.db.u32(a + L_COLOR):08x}"}
        blend = self.db.u32(a + L_BLEND)
        if blend:
            out["blend"] = blend
        for _, t in self.ptrs(a, a + 0x60):
            tex = self.single(t)
            if tex:
                out["texture"] = tex
                break
        if ty == "WidgetLayerTiledTexture":
            # Découpe en neuf de la texture : six entiers (bords et milieu, en X puis en Y).
            out["tile"] = list(struct.unpack_from("<6I", bytes(self.db.bytes(a + 0x38, 24))))
        return out

    @staticmethod
    def state_of(texture: str | None) -> str:
        if not texture:
            return "normal"
        for s in STATES:
            if texture.endswith(s):
                return s[0].lower() + s[1:]
        return "normal"

    def placement(self, a: int) -> dict:
        p = {}
        for axis, off in (("x", W_X), ("y", W_Y)):
            o = a + off
            align = self.db.u32(o)
            d = {"align": ALIGN[align] if align < len(ALIGN) else align}
            for key, k in (("high", 4), ("pos", 0x10), ("size", 0x14)):
                v = self.db.f32(o + k)
                if v:
                    d[key] = round(v, 3)
            p[axis] = d
        return p

    def widget(self, a: int, depth: int = 0) -> dict:
        db = self.db
        ty = db.vtype(a) or "?"
        w: dict = {"type": ty.replace("Widget", ""), "name": db.string(a + W_NAME), "place": self.placement(a),
                   "priority": db.i32(a + W_PRIORITY)}
        back = self.layer(db.ptr(a + W_BACK))
        if back:
            w["back"] = back
        if ty == "WidgetButton":
            tag = db.string(a + B_TEXTTAG)
            if tag:
                w["textTag"] = tag
            states: dict[str, dict] = {}
            for v in db.elements(a + B_VARIANTS, B_VARIANT_STRIDE):
                variant: dict[str, dict] = {}
                for _, t in self.ptrs(v, v + B_VARIANT_STRIDE):
                    lay = self.layer(t)
                    if lay and lay.get("texture"):
                        variant.setdefault(self.state_of(lay["texture"]), lay)
                if variant:
                    states.setdefault("variants", []).append(variant)
            if states:
                w["variants"] = states["variants"]
        elif ty == "WidgetEditLine":
            pass
        kids = []
        d = db.vec(a + W_CHILDREN)
        if d is not None and depth < 16:
            for k in range(0, d[1], 8):
                t = db.ptr(d[0] + k)
                if t is not None and (db.vtype(t) or "").startswith("Widget"):
                    kids.append(self.widget(t, depth + 1))
        if kids:
            w["children"] = kids
        return w

    def related_textures(self, group: int) -> dict[str, str]:
        """`UIRelatedTextures` : {clé: texture} (icônes des races et des classes…)."""
        out: dict[str, str] = {}
        missing: list[str] = []
        db = self.db
        for e in db.elements(group + 0x28, 40):
            key = db.string(e + 0x08)
            tex = None
            for _, t in self.ptrs(e, e + 40):
                tex = self.single(t) or (self.ui_texture(t) if db.vtype(t) == "UITexture" else None)
                if tex:
                    break
            if key and tex:
                out[key] = tex
            elif key:
                missing.append(key)
        # Références « par identifiant » (genre 2) non résolues : la texture porte le nom de la clé
        # dans le dossier des autres (les icônes du Paladin et du Prêtre ne sont que dans le pak
        # localisé `BaseLocall_x64.pak`).
        folders = {self.textures[t]["path"].rsplit("/", 1)[0] for t in out.values()}
        for key in missing:
            for folder in folders:
                tex = self.by_path(f"{folder}/{key}.(UITexture).bin")
                if tex:
                    out[key] = tex
                    break
        return out

    def by_path(self, path: str) -> str | None:
        key = re.sub(r"\.\(UITexture\)\.bin$", "", path.split("/")[-1])
        if key in self.textures:
            return key
        for pak in ["BaseLocall_x64.pak"] + [p for p in self.paks if p.startswith("Interface")]:
            z = self.zip(pak)
            try:
                data = z.read(path)
            except KeyError:
                continue
            img, _ = decode_uitexture(data)
            self.out.mkdir(parents=True, exist_ok=True)
            img.save(self.out / f"{key}.png", optimize=True)
            self.textures[key] = {"path": path, "file": f"{key}.png", "width": img.width, "height": img.height}
            return key
        return None

    def folder(self, prefix: str, trim: bool = False) -> list[str]:
        """Toutes les textures d'un dossier d'interface (états commutés par script)."""
        keys = []
        for pak in self.paks:
            if not pak.startswith("Interface"):
                continue
            z = self.zip(pak)
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if not (name.startswith(prefix) and name.endswith("(UITexture).bin")):
                    continue
                key = re.sub(r"\.\(UITexture\)\.bin$", "", name.split("/")[-1])
                if key in self.textures:
                    keys.append(key)
                    continue
                img, _ = decode_uitexture(z.read(info))
                if trim:
                    img = trim_transparent_padding(img)
                self.out.mkdir(parents=True, exist_ok=True)
                img.save(self.out / f"{key}.png", optimize=True)
                self.textures[key] = {"path": name, "file": f"{key}.png", "width": img.width, "height": img.height}
                keys.append(key)
        return keys
