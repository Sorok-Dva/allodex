import json
import zipfile
from pathlib import Path

import pytest

from tools.extract_archive import (
    build_index,
    compose_background,
    decode_subsong,
    pick_theme_subsong,
    run,
    version_key,
)

# --- pick_theme_subsong -------------------------------------------------------------------


def s(index, name, duration):
    return {"index": index, "name": name, "duration": duration}


def test_pick_theme_prefers_mainmenu_over_everything_else():
    streams = [
        s(1, "Credits_loop_NM", 332.4),
        s(2, "MainMenu_NewOrder", 188.5),
        s(3, "MainTitle", 165.9),
        s(4, "MenuAmbient", 122.7),
    ]
    assert pick_theme_subsong(streams) == 2


def test_pick_theme_prefers_the_longest_among_several_mainmenu():
    streams = [
        s(2, "MainMenu_DesertDreams", 153.6),
        s(3, "MainMenu_ThePowerOfMetal", 169.8),
        s(4, "MainTitle", 165.9),
    ]
    assert pick_theme_subsong(streams) == 3


def test_pick_theme_prefers_a_plain_stereo_theme_over_an_adaptive_multichannel_stem():
    # Banque du client 17.0 : « MainMenu_adaptive » est la plus longue mais c'est
    # un empilement de calques (4 canaux) destiné au moteur, pas un thème jouable.
    streams = [
        {"index": 3, "name": "MainMenu_HeartOfTheWorld", "duration": 173.6, "channels": 2},
        {"index": 4, "name": "MainMenu_TheBloodOfKings", "duration": 186.4, "channels": 2},
        {"index": 5, "name": "MainMenu_adaptive", "duration": 239.2, "channels": 4},
    ]
    assert pick_theme_subsong(streams) == 4


def test_pick_theme_keeps_an_adaptive_stem_when_it_is_the_only_mainmenu():
    # Banque du client 3.0 : pas d'autre thème de menu, le rang prime.
    streams = [
        {"index": 1, "name": "Credits_loop_NM", "duration": 332.4, "channels": 2},
        {"index": 2, "name": "MainMenu_adaptive", "duration": 239.2, "channels": 4},
        {"index": 3, "name": "MainTitle", "duration": 165.9, "channels": 2},
    ]
    assert pick_theme_subsong(streams) == 2


def test_pick_theme_falls_back_to_maintitle_then_menu():
    assert pick_theme_subsong([s(1, "Credits_loop_NM", 674.8), s(2, "MainTitle", 346.0), s(3, "MenuAmbient", 255.3)]) == 2
    assert pick_theme_subsong([s(1, "Credits_loop_NM", 674.8), s(3, "MenuAmbient", 255.3)]) == 3


def test_pick_theme_ignores_the_file_extension_of_old_banks():
    # Les banques FSB4 (clients 1.x/2.x) gardent l'extension dans le nom du subsong.
    streams = [s(1, "MainTitle.wav", 346.1), s(2, "MenuAmbient.wav", 255.4), s(3, "Credits1_TEST.mp3", 210.3)]
    assert pick_theme_subsong(streams) == 1


def test_pick_theme_falls_back_to_the_longest_when_no_name_matches():
    streams = [s(1, "Ambient_A", 12.0), s(2, "Ambient_B", 80.0), s(3, "Ambient_C", 30.0)]
    assert pick_theme_subsong(streams) == 2


def test_pick_theme_is_stable_when_two_candidates_tie():
    streams = [s(5, "MainMenu_B", 100.0), s(2, "MainMenu_A", 100.0)]
    assert pick_theme_subsong(streams) == 2


def test_pick_theme_on_an_empty_bank_raises():
    with pytest.raises(ValueError):
        pick_theme_subsong([])


# --- build_index --------------------------------------------------------------------------


def test_version_key_orders_numerically_not_alphabetically():
    assert version_key("9.0") < version_key("10.0")
    assert version_key("1.1") < version_key("2.0")


def test_build_index_sorts_by_version_and_keeps_media_even_when_null():
    entries = [
        {"version": "10.0", "label": "Allods Online 10.0", "media": "video"},
        {"version": "9.0", "label": "Allods Online 9.0", "media": None, "note": "client absent"},
        {"version": "1.1", "label": "Allods Online 1.1", "media": "image", "background": "background.png"},
    ]
    index = build_index(entries)
    assert [e["version"] for e in index] == ["1.1", "9.0", "10.0"]
    assert index[1]["media"] is None
    assert index[1]["note"] == "client absent"


def test_build_index_drops_empty_optional_keys_and_orders_them():
    entry = {
        "version": "16.0",
        "label": "Allods Online 16.0",
        "media": "video",
        "background": None,
        "video": {"webm": "16.0/menu.webm", "mp4": "16.0/menu.mp4"},
        "intro": None,
        "theme": {"name": "MainMenu_ThePowerOfMetal", "duration": 169.8, "ogg": "16.0/theme.ogg", "mp3": "16.0/theme.mp3"},
        "note": None,
        "theme_note": None,
    }
    (out,) = build_index([entry])
    assert list(out) == ["version", "label", "media", "video", "theme"]


# --- compose_background -------------------------------------------------------------------


def test_compose_background_covers_the_canvas_and_anchors_the_layers():
    from PIL import Image

    sky = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
    left = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    out = compose_background(
        [(sky, {"fit": "cover"}), (left, {"anchor": "bottom-left"})],
        canvas=(32, 32),
    )
    assert out.size == (32, 32)
    assert out.getpixel((31, 0))[:3] == (10, 20, 30)  # le ciel est étiré sur tout le cadre
    assert out.getpixel((0, 31))[:3] == (255, 0, 0)  # le calque est ancré en bas à gauche
    assert out.getpixel((31, 31))[:3] == (10, 20, 30)


# --- decode_subsong : repli WASM sur les banques CELT --------------------------------------


def test_decode_subsong_falls_back_to_the_wasm_build_when_the_native_one_fails(tmp_path, monkeypatch):
    calls = []

    def boom(vgmstream, fsb, subsong, wav):
        calls.append("natif")
        raise RuntimeError("vgmstream a échoué (code -11)")

    def fake_run(cmd, **kwargs):
        calls.append("wasm")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"RIFF")
        return type("R", (), {"returncode": 0, "stderr": b"", "stdout": b""})()

    wasm = tmp_path / "vgmstream-node-wrapper.js"
    wasm.write_text("", encoding="utf-8")
    monkeypatch.setattr("tools.extract_archive.run_vgmstream", boom)
    monkeypatch.setattr("tools.extract_archive.subprocess.run", fake_run)

    wav = tmp_path / "out.wav"
    decode_subsong(Path("/nonexistent/vgmstream"), wasm, tmp_path / "bank.fsb", 2, wav)

    assert calls == ["natif", "wasm"]
    assert wav.exists()


def test_decode_subsong_reraises_when_no_wasm_build_is_available(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("vgmstream a échoué (code -11)")

    monkeypatch.setattr("tools.extract_archive.run_vgmstream", boom)
    with pytest.raises(RuntimeError):
        decode_subsong(Path("/nonexistent/vgmstream"), tmp_path / "absent.js", tmp_path / "b.fsb", 1, tmp_path / "o.wav")


# --- run : tolérance aux clients absents ---------------------------------------------------


def _manifest(root: str) -> dict:
    return {
        "clients": {"test": {"root": root}},
        "versions": [
            {
                "version": "2.0",
                "label": "Allods Online 2.0",
                "client": "test",
                "background": {"pak": "Interface.pak", "entry": "Interface/Wrap/MainMenu/Main2/Background.(UITexture).bin"},
                "theme": {"pak": "SFX_Music.pak", "entry": "SFX/Music/Music_Menu.fsb"},
                "note": "note du manifeste",
            },
            {
                "version": "16.0",
                "label": "Allods Online 16.0",
                "client": "test",
                "video": {"pak": "Video.pak", "entry": "Video/16_0Events/MainMenu/MainMenu.ogv"},
            },
        ],
    }


def test_run_warns_and_keeps_a_null_media_entry_when_the_client_is_absent(tmp_path):
    manifest = _manifest(str(tmp_path / "disque-absent"))
    index, report = run(manifest, tmp_path / "out", Path("/nonexistent/vgmstream"), force=False)

    assert [e["version"] for e in index] == ["2.0", "16.0"]
    assert all(e["media"] is None for e in index)
    assert all("client absent" in e["note"] for e in index)
    assert "note du manifeste" in index[0]["note"]
    assert len(report) == 2 and all(line.startswith("AVERTISSEMENT") for line in report)


def test_run_only_restricts_the_extraction_to_one_version(tmp_path):
    manifest = _manifest(str(tmp_path / "disque-absent"))
    index, _ = run(manifest, tmp_path / "out", Path("/nonexistent/vgmstream"), force=False, only=["16.0"])
    assert [e["version"] for e in index] == ["16.0"]


def test_run_only_keeps_the_versions_already_extracted_in_the_index(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "out.json").write_text(
        json.dumps([{"version": "2.0", "label": "Allods Online 2.0", "media": "image", "background": "background.png"}]),
        encoding="utf-8",
    )
    manifest = _manifest(str(tmp_path / "disque-absent"))
    index, _ = run(manifest, out, Path("/nonexistent/vgmstream"), force=False, only=["16.0"])

    assert [e["version"] for e in index] == ["2.0", "16.0"]
    assert index[0]["media"] == "image"


def test_parse_metadata_uses_the_stream_length_not_the_looped_play_duration():
    from tools.extract_archive import _parse_metadata

    meta = _parse_metadata(
        "sample rate: 44100 Hz\n"
        "stream total samples: 9463808 (3:34.599 seconds)\n"
        "stream count: 3\n"
        "stream name: MainMenu_LordsOfDestiny_lpp\n"
        "play duration: 18372377 samples (6:56.607 seconds)\n"
    )
    assert meta["name"] == "MainMenu_LordsOfDestiny_lpp"
    assert meta["duration"] == pytest.approx(214.599, abs=0.01)
    assert meta["count"] == 3


def test_run_warns_when_the_pak_or_the_entry_is_missing(tmp_path, monkeypatch):
    client = tmp_path / "client"
    client.mkdir()
    with zipfile.ZipFile(client / "Interface.pak", "w") as zf:
        zf.writestr("autre.bin", b"x")
    manifest = _manifest(str(client))
    manifest["versions"] = manifest["versions"][:1]
    monkeypatch.setattr("tools.extract_archive.extract_theme", lambda *a, **k: (None, "banque absente"))

    index, report = run(manifest, tmp_path / "out", Path("/nonexistent/vgmstream"), force=False)

    assert index[0]["media"] is None
    assert "background" not in index[0]
    assert any("Background" in line for line in report)


def test_run_records_the_theme_and_the_background_written_by_the_helpers(tmp_path, monkeypatch):
    client = tmp_path / "client"
    client.mkdir()
    with zipfile.ZipFile(client / "Interface.pak", "w") as zf:
        zf.writestr("Interface/Wrap/MainMenu/Main2/Background.(UITexture).bin", b"x")
    with zipfile.ZipFile(client / "SFX_Music.pak", "w") as zf:
        zf.writestr("SFX/Music/Music_Menu.fsb", b"FSB5")
    manifest = _manifest(str(client))
    manifest["versions"] = manifest["versions"][:1]

    def fake_background(data, spec, pak, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        return None

    monkeypatch.setattr("tools.extract_archive.write_background", fake_background)
    monkeypatch.setattr(
        "tools.extract_archive.extract_theme",
        lambda *a, **k: ({"name": "MainTitle", "duration": 346.0, "alternatives": ["MenuAmbient"]}, None),
    )

    out = tmp_path / "out"
    index, report = run(manifest, out, Path("/nonexistent/vgmstream"), force=False)

    assert report == []
    assert index[0]["media"] == "image"
    assert index[0]["background"] == "background.png"
    assert index[0]["theme"]["name"] == "MainTitle"
    assert (out / "2.0" / "background.png").exists()


def test_main_writes_the_index_next_to_the_output_directory(tmp_path, monkeypatch):
    manifest_path = tmp_path / "clients_manifest.json"
    manifest_path.write_text(json.dumps(_manifest(str(tmp_path / "absent"))), encoding="utf-8")
    out = tmp_path / "archive"
    monkeypatch.setattr("tools.extract_archive.shutil.which", lambda name: "/usr/bin/" + name)

    code = __import__("tools.extract_archive", fromlist=["main"]).main(
        ["--manifest", str(manifest_path), "--out", str(out), "--vgmstream", str(tmp_path / "vgmstream")]
    )

    assert code == 0
    index = json.loads((tmp_path / "archive.json").read_text(encoding="utf-8"))
    assert [e["version"] for e in index] == ["2.0", "16.0"]
