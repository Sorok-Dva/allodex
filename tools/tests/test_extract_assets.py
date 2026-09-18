from tools.extract_assets import select_entries, output_path_for

MANIFEST = {
    "texture_prefixes": ["Interface/Ingame/Medals/Textures/"],
    "texture_files": ["Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin"],
}


def test_select_entries_keeps_prefix_matches_and_explicit_files():
    names = [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Ingame/Medals/Scripts/ClassMain.luac",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
        "Interface/Icons/Misc/Event/SilverMedal.(UITexture).bin",
    ]
    assert select_entries(names, MANIFEST) == [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
    ]


def test_output_path_strips_type_suffix():
    assert output_path_for("Interface/Ingame/Medals/Textures/Numbers/Num1.(UITexture).bin") == \
        "Interface/Ingame/Medals/Textures/Numbers/Num1"


def test_select_entries_rejects_path_traversal():
    # Même explicitement listée, une entrée à chemin dangereux doit être rejetée :
    # `output_path_for` la transformerait en chemin de sortie hors du dossier cible.
    manifest = {
        "texture_prefixes": [],
        "texture_files": ["../x.(UITexture).bin"],
    }
    assert select_entries(["../x.(UITexture).bin"], manifest) == []
