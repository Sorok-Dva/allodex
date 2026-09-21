"""4.0 « Lords of Destiny » : l'île au château sous son dôme de ciel.

Un seul objet (`Animated_Background`), aucun composant attaché : l'exportateur générique
suffit pour la géométrie, les textures, les matériaux et l'animation squelettique (oiseaux,
cristaux). Ce que le glTF ne porte pas, c'est **l'ordre de peinture** du moteur : le
`(Geometry).xdb` déclare `sortMode OFFSETS`, c'est-à-dire que les éléments sont peints dans
l'ordre où ils se suivent dans l'index buffer — le dôme (Back2/Back3) d'abord, l'île, le
soleil, le château, la brume, puis les nuages de premier plan — sans tri par profondeur. Le
crochet ci-dessous relève ce mode dans `scene.json` pour que le lecteur l'applique à la place
de son tri par profondeur moyenne, qui faisait passer le dôme par-dessus l'île (le « voile »).
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from tools.scenes import SceneHooks

GEOMETRY = "World/MainMenu/Animated_Background/Animated_Background.(Geometry).xdb"


def read_sort_mode(xdb_text: str) -> str | None:
    """`<sortMode>` du Geometry xdb (`OFFSETS` = ordre du fichier), `None` s'il manque."""
    try:
        root = ET.fromstring(xdb_text)
    except ET.ParseError:
        return None
    text = root.findtext("sortMode")
    return text.strip() if text else None


def after_export(target: Path, meta: dict, source, server_root: Path) -> None:
    path = Path(server_root) / GEOMETRY
    if not path.is_file():
        return
    mode = read_sort_mode(path.read_text(errors="replace"))
    if mode:
        meta["sortMode"] = mode


HOOKS = SceneHooks(after_export=after_export)
