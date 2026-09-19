import json
import zipfile
from pathlib import Path

import pytest

from tools.extract_archive import (
    CAPTURE_PENDING_NOTE,
    build_index,
    build_label,
    compose_background,
    decode_subsong,
    extract_logo,
    extract_theme,
    fsb_subsong_count,
    logo_candidates,
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


# --- build_label --------------------------------------------------------------------------


def test_build_label_joins_the_addon_name_and_the_version():
    assert build_label("Game of Gods", "3.0") == "Allods Online - Game of Gods (3.0)"
    assert build_label("Power of Metal", "16.0") == "Allods Online - Power of Metal (16.0)"


def test_build_label_without_a_name_keeps_only_the_version():
    # 1.1 est antérieure aux add-ons : pas de sous-titre à afficher.
    assert build_label(None, "1.1") == "Allods Online (1.1)"
    assert build_label("   ", "1.1") == "Allods Online (1.1)"


def test_run_builds_the_label_from_the_name_of_the_manifest(tmp_path):
    index, _ = run(_manifest(str(tmp_path / "absent")), tmp_path / "out", Path("/nonexistent/vgmstream"))
    assert [e["label"] for e in index] == [
        "Allods Online - Conquerors of Time (2.0)",
        "Allods Online - Power of Metal (16.0)",
    ]
    assert index[0]["name"] == "Conquerors of Time"


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


# --- fsb_subsong_count --------------------------------------------------------------------


def _fsb5(count: int, tail: bytes = b"\0" * 16) -> bytes:
    # FSB5 : magic, version, nombre d'échantillons (8..12), taille des en-têtes…
    return b"FSB5" + (1).to_bytes(4, "little") + count.to_bytes(4, "little") + tail


def _fsb4(count: int, tail: bytes = b"\0" * 16) -> bytes:
    # FSB4/FSB3/FSB2 : magic, nombre d'échantillons (4..8), taille de la table d'en-têtes (8..12).
    return b"FSB4" + count.to_bytes(4, "little") + (336).to_bytes(4, "little") + tail


def test_fsb_subsong_count_reads_offset_8_on_fsb5():
    assert fsb_subsong_count(_fsb5(5)) == 5


def test_fsb_subsong_count_reads_offset_4_on_fsb4():
    # La banque du client 1.1 : 4 subsongs, et 336 en 8..12 (la taille des en-têtes,
    # que la lecture FSB5 prenait à tort pour un nombre de subsongs).
    payload = _fsb4(4)
    assert fsb_subsong_count(payload) == 4
    assert int.from_bytes(payload[8:12], "little") == 336


def test_fsb_subsong_count_handles_the_other_fsb_generations():
    assert fsb_subsong_count(b"FSB3" + (7).to_bytes(4, "little") + b"\0" * 16) == 7


def test_fsb_subsong_count_returns_none_on_a_non_fsb_or_truncated_buffer():
    assert fsb_subsong_count(b"RIFF" + b"\0" * 32) is None
    assert fsb_subsong_count(b"OggS" + b"\0" * 32) is None
    assert fsb_subsong_count(b"FSB5\0\0") is None  # tronqué
    assert fsb_subsong_count(b"") is None


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
                "name": "Conquerors of Time",
                "client": "test",
                "background": {"pak": "Interface.pak", "entry": "Interface/Wrap/MainMenu/Main2/Background.(UITexture).bin"},
                "theme": {"pak": "SFX_Music.pak", "entry": "SFX/Music/Music_Menu.fsb"},
                "note": "note du manifeste",
            },
            {
                "version": "16.0",
                "name": "Power of Metal",
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


# --- idempotence et --force ----------------------------------------------------------------


class _Spies:
    """Compte les appels aux étapes coûteuses (décodage, encodage, transcodage)."""

    def __init__(self):
        self.background = 0
        self.video = 0
        self.decode = 0
        self.encode = 0

    @property
    def total(self) -> int:
        return self.background + self.video + self.decode + self.encode


def _fake_client(tmp_path: Path) -> Path:
    """Client minimal : les trois paks du manifeste de test, avec les entrées attendues."""
    client = tmp_path / "client"
    client.mkdir()
    with zipfile.ZipFile(client / "Interface.pak", "w") as zf:
        zf.writestr("Interface/Wrap/MainMenu/Main2/Background.(UITexture).bin", b"texture")
    with zipfile.ZipFile(client / "SFX_Music.pak", "w") as zf:
        zf.writestr("SFX/Music/Music_Menu.fsb", _fsb5(1, b"\0" * 64))
    with zipfile.ZipFile(client / "Video.pak", "w") as zf:
        zf.writestr("Video/16_0Events/MainMenu/MainMenu.ogv", b"ogv")
    return client


def _spy_on_the_expensive_steps(monkeypatch) -> _Spies:
    spies = _Spies()

    def fake_background(data, spec, pak, target):
        spies.background += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        return None

    def fake_video(data, out_base):
        spies.video += 1
        out_base.parent.mkdir(parents=True, exist_ok=True)
        out_base.with_suffix(".webm").write_bytes(b"webm")
        out_base.with_suffix(".mp4").write_bytes(b"mp4")
        return 12.0, None

    def fake_decode(vgmstream, wasm, fsb, subsong, wav):
        spies.decode += 1
        wav.write_bytes(b"RIFF")

    def fake_encode(wav, out_base, category):
        spies.encode += 1
        out_base.with_suffix(".ogg").write_bytes(b"ogg")
        out_base.with_suffix(".mp3").write_bytes(b"mp3")

    monkeypatch.setattr("tools.extract_archive.write_background", fake_background)
    monkeypatch.setattr("tools.extract_archive.extract_video", fake_video)
    monkeypatch.setattr("tools.extract_archive.decode_subsong", fake_decode)
    monkeypatch.setattr("tools.extract_archive.encode_outputs", fake_encode)
    monkeypatch.setattr("tools.extract_archive.fold_to_stereo", lambda wav: wav)
    monkeypatch.setattr("tools.extract_archive.probe_duration", lambda path: 168.0)
    monkeypatch.setattr(
        "tools.extract_archive.list_subsongs",
        lambda vgmstream, fsb, payload: [{"index": 1, "name": "MainTitle", "duration": 168.0, "channels": 2}],
    )
    return spies


def test_run_is_idempotent_and_leaves_existing_outputs_alone(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    spies = _spy_on_the_expensive_steps(monkeypatch)
    out = tmp_path / "out"
    for version, files in (("2.0", ("background.png", "theme.ogg", "theme.mp3")), ("16.0", ("menu.webm", "menu.mp4"))):
        (out / version).mkdir(parents=True)
        for name in files:
            (out / version / name).write_bytes(b"deja-la")

    index, report = run(_manifest(str(client)), out, Path("/nonexistent/vgmstream"), force=False)

    assert spies.total == 0, "aucune sortie existante ne doit être redécodée sans --force"
    assert [e["version"] for e in index] == ["2.0", "16.0"]
    assert index[0]["media"] == "image" and index[0]["background"] == "background.png"
    assert index[0]["theme"]["name"] == "MainTitle"
    assert index[1]["media"] == "video" and index[1]["video"] == {"webm": "menu.webm", "mp4": "menu.mp4"}
    assert report == []
    assert (out / "2.0" / "background.png").read_bytes() == b"deja-la"
    assert (out / "16.0" / "menu.webm").read_bytes() == b"deja-la"


def test_run_force_redoes_every_step_even_when_the_outputs_exist(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    spies = _spy_on_the_expensive_steps(monkeypatch)
    out = tmp_path / "out"
    for version, files in (("2.0", ("background.png", "theme.ogg", "theme.mp3")), ("16.0", ("menu.webm", "menu.mp4"))):
        (out / version).mkdir(parents=True)
        for name in files:
            (out / version / name).write_bytes(b"deja-la")

    index, report = run(_manifest(str(client)), out, Path("/nonexistent/vgmstream"), force=True)

    assert (spies.background, spies.video, spies.decode, spies.encode) == (1, 1, 1, 1)
    assert report == []
    assert [e["version"] for e in index] == ["2.0", "16.0"]
    assert (out / "2.0" / "background.png").read_bytes() == b"png"
    assert (out / "16.0" / "menu.webm").read_bytes() == b"webm"


# --- fond : capture de la scène 3D, sinon illustration de repli -----------------------------


def _capture_manifest(root: str, capture: str = "refs/menu-2.0.png") -> dict:
    manifest = _manifest(root)
    manifest["versions"] = manifest["versions"][:1]
    manifest["versions"][0]["background"]["capture"] = capture
    return manifest


def test_run_uses_the_screen_capture_as_background_when_the_file_exists(tmp_path, monkeypatch):
    from PIL import Image

    client = _fake_client(tmp_path)
    spies = _spy_on_the_expensive_steps(monkeypatch)
    captures = tmp_path / "captures"
    (captures / "refs").mkdir(parents=True)
    Image.new("RGB", (1920, 1009), (12, 34, 56)).save(captures / "refs" / "menu-2.0.png")

    out = tmp_path / "out"
    index, report = run(_capture_manifest(str(client)), out, Path("/nonexistent/vgmstream"), capture_root=captures)

    assert report == []
    assert index[0]["media"] == "image" and index[0]["background"] == "background.png"
    assert "background_note" not in index[0], "une vraie capture ne porte pas la mention de repli"
    assert spies.background == 0, "la capture remplace la texture du client, on ne décode rien"
    with Image.open(out / "2.0" / "background.png") as written:
        assert written.size == (1920, 1009)  # aucun recadrage


def test_run_falls_back_to_the_client_texture_and_notes_it_when_the_capture_is_missing(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    spies = _spy_on_the_expensive_steps(monkeypatch)
    out = tmp_path / "out"

    index, report = run(_capture_manifest(str(client)), out, Path("/nonexistent/vgmstream"),
                        capture_root=tmp_path / "captures")

    assert report == []
    assert index[0]["media"] == "image" and index[0]["background"] == "background.png"
    assert index[0]["background_note"] == CAPTURE_PENDING_NOTE
    assert spies.background == 1


def test_run_replaces_an_existing_fallback_background_as_soon_as_the_capture_appears(tmp_path, monkeypatch):
    from PIL import Image

    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    out = tmp_path / "out"
    (out / "2.0").mkdir(parents=True)
    (out / "2.0" / "background.png").write_bytes(b"illustration-de-repli")
    captures = tmp_path / "captures"
    (captures / "refs").mkdir(parents=True)
    Image.new("RGB", (1920, 1009), (12, 34, 56)).save(captures / "refs" / "menu-2.0.png")

    # Sans --force : la capture prime quand même, sinon la version resterait sur le repli.
    index, _ = run(_capture_manifest(str(client)), out, Path("/nonexistent/vgmstream"), capture_root=captures)

    assert "background_note" not in index[0]
    with Image.open(out / "2.0" / "background.png") as written:
        assert written.size == (1920, 1009)


# --- logo ----------------------------------------------------------------------------------


def test_logo_candidates_prefers_french_then_english_then_the_unlocalised_texture():
    assert logo_candidates("W/WrapAllodsLogoV16") == [
        "W/WrapAllodsLogoV16.fra.(UITexture).bin",
        "W/WrapAllodsLogoV16.fr.(UITexture).bin",
        "W/WrapAllodsLogoV16.eng_eu.(UITexture).bin",
        "W/WrapAllodsLogoV16.eng.(UITexture).bin",
        "W/WrapAllodsLogoV16.(UITexture).bin",
    ]


def _logo_pak(path: Path, base: str, locales) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for loc in locales:
            zf.writestr(f"{base}.{loc}.(UITexture).bin" if loc else f"{base}.(UITexture).bin", loc or "ru")


def _decode_to_marker(monkeypatch) -> list[str]:
    """Remplace le décodage DXT et note la variante lue (chaque entrée du pak factice
    a pour contenu le nom de sa locale). La liste renvoyée est le journal des lectures."""
    from PIL import Image

    seen: list[str] = []

    def fake(data: bytes) -> Image.Image:
        seen.append(data.decode())
        return Image.new("RGBA", (4, 4), (0, 0, 0, 0))

    monkeypatch.setattr("tools.extract_archive._decode_texture", fake)
    return seen


BASE = "Interface/Common/Elements/WrapAllodsLogo/WrapAllodsLogoV7"


def test_extract_logo_picks_the_french_variant_over_the_others(tmp_path, monkeypatch):
    seen = _decode_to_marker(monkeypatch)
    client = tmp_path / "client"
    client.mkdir()
    _logo_pak(client / "Interface.Mini.pak", BASE, [None, "eng_eu", "fra", "ger", "tr"])

    name, err = extract_logo({"pak": "Interface.Mini.pak", "entry": BASE}, client, tmp_path / "logo.png", force=False)

    assert (name, err) == ("logo.png", None)
    assert seen == ["fra"]
    assert (tmp_path / "logo.png").exists()


def test_extract_logo_falls_back_to_english_then_to_the_unlocalised_texture(tmp_path, monkeypatch):
    seen = _decode_to_marker(monkeypatch)
    client = tmp_path / "client"
    client.mkdir()
    _logo_pak(client / "eng.pak", BASE, [None, "eng_eu", "tw"])
    _logo_pak(client / "ru.pak", BASE, [None])

    name, err = extract_logo({"pak": ["eng.pak", "ru.pak"], "entry": BASE}, client, tmp_path / "a.png", force=False)
    assert (name, err) == ("a.png", None)

    russian, err2 = extract_logo({"pak": "ru.pak", "entry": BASE}, client, tmp_path / "b.png", force=False)
    assert (russian, err2) == ("b.png", None)
    assert seen == ["eng_eu", "ru"]


def test_extract_logo_prefers_the_language_over_the_order_of_the_paks(tmp_path, monkeypatch):
    # Les logos récents sont éclatés entre plusieurs paks : la langue prime sur le pak.
    seen = _decode_to_marker(monkeypatch)
    client = tmp_path / "client"
    client.mkdir()
    _logo_pak(client / "Interface.Mini.pak", BASE, ["eng"])
    _logo_pak(client / "BaseLocfra_x64.pak", BASE, ["fra"])

    name, err = extract_logo(
        {"pak": ["Interface.Mini.pak", "BaseLocfra_x64.pak"], "entry": BASE}, client, tmp_path / "logo.png", force=False,
    )

    assert (name, err) == ("logo.png", None)
    assert seen == ["fra"]


def test_extract_logo_reports_a_missing_logo_without_writing_anything(tmp_path, monkeypatch):
    _decode_to_marker(monkeypatch)
    client = tmp_path / "client"
    client.mkdir()
    _logo_pak(client / "Interface.Mini.pak", BASE + "V99", ["fra"])

    name, err = extract_logo({"pak": "Interface.Mini.pak", "entry": BASE}, client, tmp_path / "logo.png", force=False)

    assert name is None and "logo introuvable" in err
    assert not (tmp_path / "logo.png").exists()


def test_run_records_the_logo_in_the_index(tmp_path, monkeypatch):
    _decode_to_marker(monkeypatch)
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    _logo_pak(client / "BaseLocfra.pak", BASE, ["fra"])
    manifest = _manifest(str(client))
    manifest["versions"] = manifest["versions"][:1]
    manifest["versions"][0]["logo"] = {"pak": "BaseLocfra.pak", "entry": BASE}

    index, report = run(manifest, tmp_path / "out", Path("/nonexistent/vgmstream"))

    assert report == []
    assert index[0]["logo"] == "logo.png"
    assert (tmp_path / "out" / "2.0" / "logo.png").exists()


def test_run_leaves_the_logo_out_of_the_index_when_the_manifest_has_none(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    index, _ = run(_manifest(str(client)), tmp_path / "out", Path("/nonexistent/vgmstream"))
    assert "logo" not in index[0]


# --- emblème commun ------------------------------------------------------------------------


def test_run_extracts_the_shared_loading_emblem_once(tmp_path, monkeypatch):
    _decode_to_marker(monkeypatch)
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    with zipfile.ZipFile(client / "Interface.Mini.pak", "w") as zf:
        zf.writestr("Interface/Wrap/SystemState/LoadingScreen2/LoadingGlobeFront.(UITexture).bin", "globe")
    manifest = _manifest(str(client))
    manifest["common"] = {
        "client": "test",
        "pak": "Interface.Mini.pak",
        "textures": {"loading-globe.png": "Interface/Wrap/SystemState/LoadingScreen2/LoadingGlobeFront.(UITexture).bin"},
    }

    out = tmp_path / "out"
    _, report = run(manifest, out, Path("/nonexistent/vgmstream"))

    assert report == []
    assert (out / "_common" / "loading-globe.png").exists()


# --- thème absent des clients archivés -----------------------------------------------------


def test_run_keeps_a_version_without_theme_and_carries_its_note(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    manifest = _manifest(str(client))
    manifest["versions"] = manifest["versions"][:1]
    manifest["versions"][0]["theme"] = None
    manifest["versions"][0]["theme_note"] = "Thème non disponible dans les clients archivés"

    index, report = run(manifest, tmp_path / "out", Path("/nonexistent/vgmstream"))

    assert report == []
    assert "theme" not in index[0]
    assert index[0]["theme_note"] == "Thème non disponible dans les clients archivés"


def test_run_does_not_resurrect_a_theme_removed_from_the_manifest(tmp_path, monkeypatch):
    # L'index précédent gardait une approximation : `theme: null` doit l'effacer.
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "out.json").write_text(
        json.dumps([{
            "version": "2.0", "label": "Allods Online 2.0", "media": "image", "background": "background.png",
            "theme": {"name": "MainMenu_CapitalOfShadows", "duration": 161.5, "ogg": "theme.ogg", "mp3": "theme.mp3"},
        }]),
        encoding="utf-8",
    )
    manifest = _manifest(str(client))
    manifest["versions"] = manifest["versions"][:1]
    manifest["versions"][0]["theme"] = None

    index, _ = run(manifest, out, Path("/nonexistent/vgmstream"))

    assert "theme" not in index[0]


def test_extract_theme_prefer_overrides_the_automatic_choice(tmp_path, monkeypatch):
    client = _fake_client(tmp_path)
    _spy_on_the_expensive_steps(monkeypatch)
    streams = [
        {"index": 2, "name": "MainMenu_DesertDreams", "duration": 153.6, "channels": 2},
        {"index": 3, "name": "MainMenu_CapitalOfShadows", "duration": 161.5, "channels": 2},
    ]
    monkeypatch.setattr("tools.extract_archive.list_subsongs", lambda *a: streams)
    spec = {"pak": "SFX_Music.pak", "entry": "SFX/Music/Music_Menu.fsb"}

    auto, err = extract_theme(spec, client, tmp_path / "auto", Path("/nonexistent/vgmstream"), force=False)
    forced, err2 = extract_theme(
        {**spec, "prefer": "MainMenu_DesertDreams"}, client, tmp_path / "forced",
        Path("/nonexistent/vgmstream"), force=False,
    )

    assert (err, err2) == (None, None)
    assert auto["name"] == "MainMenu_CapitalOfShadows" and auto["subsong"] == 3  # la plus longue
    assert forced["name"] == "MainMenu_DesertDreams" and forced["subsong"] == 2
    assert forced["alternatives"] == ["MainMenu_CapitalOfShadows"]


def test_extract_theme_from_url_downloads_encodes_and_indexes(tmp_path, monkeypatch):
    from tools import extract_archive as ea

    calls = {}

    def fake_download(url, target):
        calls["url"] = url
        target.write_bytes(b"mp3")

    def fake_encode(src, out_base, category):
        assert src.read_bytes() == b"mp3" and category == "tracks"
        out_base.with_suffix(".ogg").write_bytes(b"ogg")
        out_base.with_suffix(".mp3").write_bytes(b"mp3")

    monkeypatch.setattr(ea, "download", fake_download)
    monkeypatch.setattr(ea, "encode_outputs", fake_encode)
    monkeypatch.setattr(ea, "probe_duration", lambda p: 174.456)

    spec = {"url": "https://allods.ru/media/mp3/abc.mp3", "name": "MainMenu_SoulOfDarkness"}
    theme, err = ea.extract_theme_from_url(spec, tmp_path / "11.0", force=False)

    assert err is None
    assert calls["url"] == spec["url"]
    assert theme == {"name": "MainMenu_SoulOfDarkness", "duration": 174.456, "ogg": "theme.ogg", "mp3": "theme.mp3", "source": spec["url"]}
    # Idempotent : les fichiers existent, plus de téléchargement sans --force.
    calls.clear()
    ea.extract_theme_from_url(spec, tmp_path / "11.0", force=False)
    assert calls == {}


def test_extract_theme_from_url_reports_a_network_failure(tmp_path, monkeypatch):
    from tools import extract_archive as ea

    def failing(url, target):
        raise OSError("hors ligne")

    monkeypatch.setattr(ea, "download", failing)
    theme, err = ea.extract_theme_from_url({"url": "https://x/y.mp3"}, tmp_path / "v", force=True)
    assert theme is None and "téléchargement impossible" in err and "hors ligne" in err


def test_extract_logo_from_url_downloads_and_trims_the_png(tmp_path, monkeypatch):
    from PIL import Image
    from tools import extract_archive as ea

    def fake_download(url, target):
        img = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
        img.paste((255, 0, 0, 255), (0, 0, 40, 20))  # logo ancré en haut à gauche, padding transparent
        img.save(target, format="PNG")

    monkeypatch.setattr(ea, "download", fake_download)
    name, err = ea.extract_logo_from_url({"url": "https://x/logo.png"}, tmp_path / "10.0" / "logo.png", force=False)
    assert err is None and name == "logo.png"
    with Image.open(tmp_path / "10.0" / "logo.png") as out:
        assert out.size == (40, 20)

    monkeypatch.setattr(ea, "download", lambda url, target: (_ for _ in ()).throw(OSError("404")))
    assert ea.extract_logo_from_url({"url": "https://x/logo.png"}, tmp_path / "10.0" / "logo.png", force=False) == ("logo.png", None), "déjà extrait : pas de nouveau téléchargement"
    name, err = ea.extract_logo_from_url({"url": "https://x/nope.png"}, tmp_path / "11.0" / "logo.png", force=True)
    assert name is None and "logo introuvable" in err


def test_extract_theme_from_file_encodes_a_local_mp3_relative_to_the_repo(tmp_path, monkeypatch):
    from tools import extract_archive as ea

    (tmp_path / "refs").mkdir()
    (tmp_path / "refs" / "t.mp3").write_bytes(b"mp3")
    monkeypatch.setattr(ea, "encode_outputs", lambda src, out_base, cat: [out_base.with_suffix(s).write_bytes(b"x") for s in (".ogg", ".mp3")])
    monkeypatch.setattr(ea, "probe_duration", lambda p: 187.4)

    theme, err = ea.extract_theme_from_url({"file": "refs/t.mp3", "name": "MainMenu_CallOfLegends"}, tmp_path / "14.0", force=True, base_dir=tmp_path)
    assert err is None and theme["name"] == "MainMenu_CallOfLegends" and theme["source"] == "refs/t.mp3"
    theme, err = ea.extract_theme_from_url({"file": "refs/absent.mp3"}, tmp_path / "x", force=True, base_dir=tmp_path)
    assert theme is None and "fichier introuvable" in err
