import io
import json
import shutil
import struct
import wave
import zipfile
from pathlib import Path

import pytest

from tools.allods_packdb import packs_path
from tools.extract_audio import (
    extract_pak_entry_bytes,
    fsb_payload_from_bytes,
    fsb_subsong_count,
    is_safe_entry,
    iter_entries,
    resolve_pak_path,
    run,
)

MANIFEST = {
    "packs": {
        "music": "data/Packs/SFX_Music.Mini.pak",
        "interface": "data/Packs/SFX_Interface.Mini.pak",
    },
    "tracks": {
        "menu": {"pak": "music", "entry": "SFX/Music/Music_Menu.fsb", "subsong": 2},
    },
    "sfx": {
        "medals-open": {"pak": "interface", "entry": "SFX/Interface/Interface.bsb", "subsong": 109},
    },
}


# --- sélection / résolution de manifeste --------------------------------------------------

def test_iter_entries_yields_tracks_then_sfx_with_category():
    items = list(iter_entries(MANIFEST))
    assert items == [
        ("tracks", "menu", MANIFEST["tracks"]["menu"]),
        ("sfx", "medals-open", MANIFEST["sfx"]["medals-open"]),
    ]


def test_resolve_pak_path_uses_packs_key():
    client = Path("/client")
    assert resolve_pak_path(client, MANIFEST, "music") == client / "data/Packs/SFX_Music.Mini.pak"


def test_resolve_pak_path_falls_back_to_literal_relative_path():
    client = Path("/client")
    assert resolve_pak_path(client, MANIFEST, "data/Packs/Other.pak") == client / "data/Packs/Other.pak"


def test_is_safe_entry_rejects_traversal_and_absolute_paths():
    assert not is_safe_entry("../x.fsb")
    assert not is_safe_entry("/etc/passwd")
    assert not is_safe_entry("C:/x.fsb")
    assert is_safe_entry("SFX/Music/Music_Menu.fsb")


# --- FSB / BSB helpers -----------------------------------------------------------------

def _fsb_header(subsong_count: int) -> bytes:
    # FSB5\x01\x00\x00\x00<count u32le> ... (le reste importe peu pour ces tests)
    return b"FSB5" + b"\x01\x00\x00\x00" + struct.pack("<I", subsong_count) + b"\x00" * 8


def test_fsb_payload_from_bytes_passes_through_raw_fsb():
    data = _fsb_header(5) + b"payload"
    assert fsb_payload_from_bytes(data, "SFX/Music/Music_Menu.fsb") == data


def test_fsb_payload_from_bytes_rejects_fsb_without_magic():
    assert fsb_payload_from_bytes(b"not an fsb", "SFX/Music/Music_Menu.fsb") is None


def test_fsb_payload_from_bytes_decompresses_bsb_and_finds_magic():
    import zlib

    inner = _fsb_header(3) + b"payload"
    compressed = zlib.compress(inner)
    assert fsb_payload_from_bytes(compressed, "SFX/Interface/Interface.bsb") == inner


def test_fsb_payload_from_bytes_rejects_bsb_with_bad_zlib():
    assert fsb_payload_from_bytes(b"not zlib data", "SFX/Interface/Interface.bsb") is None


def test_fsb_subsong_count_reads_header_field():
    assert fsb_subsong_count(_fsb_header(118)) == 118


def test_fsb_subsong_count_none_for_unknown_magic():
    assert fsb_subsong_count(b"XXXX" + b"\x00" * 20) is None


# --- extraction depuis un pak (zip) -----------------------------------------------------

def _make_pak(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    pak = tmp_path / "Test.pak"
    with zipfile.ZipFile(pak, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return pak


def test_extract_pak_entry_bytes_reads_existing_entry(tmp_path):
    pak = _make_pak(tmp_path, {"SFX/Music/Music_Menu.fsb": b"hello"})
    assert extract_pak_entry_bytes(pak, "SFX/Music/Music_Menu.fsb") == b"hello"


def test_extract_pak_entry_bytes_none_for_missing_pak(tmp_path):
    assert extract_pak_entry_bytes(tmp_path / "missing.pak", "SFX/Music/Music_Menu.fsb") is None


def test_extract_pak_entry_bytes_none_for_missing_entry(tmp_path):
    pak = _make_pak(tmp_path, {"SFX/Music/Music_Menu.fsb": b"hello"})
    assert extract_pak_entry_bytes(pak, "SFX/Music/Other.fsb") is None


def test_extract_pak_entry_bytes_none_for_unsafe_entry(tmp_path):
    pak = _make_pak(tmp_path, {"SFX/Music/Music_Menu.fsb": b"hello"})
    assert extract_pak_entry_bytes(pak, "../escape.fsb") is None


# --- pipeline complet (décodeur vgmstream monkeypatché, pas de dépendance à vgmstream) ---

def _write_silent_wav(path: Path, seconds: float = 0.2) -> None:
    n_frames = int(44100 * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * n_frames)


@pytest.fixture
def fake_vgmstream(monkeypatch):
    """Remplace l'appel à vgmstream-cli par l'écriture d'un WAV silencieux, pour ne pas
    dépendre du binaire vgmstream dans les tests."""
    calls = {"n": 0}

    def fake_run(vgmstream, fsb_path, subsong, out_wav):
        calls["n"] += 1
        _write_silent_wav(out_wav)

    monkeypatch.setattr("tools.extract_audio.run_vgmstream", fake_run)
    return calls


@pytest.fixture(autouse=True)
def _require_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe requis pour encoder/mesurer les sorties de test")


def _client_with_paks(tmp_path: Path) -> Path:
    client = tmp_path / "client"
    (client / "data" / "Packs").mkdir(parents=True)
    with zipfile.ZipFile(client / "data" / "Packs" / "SFX_Music.Mini.pak", "w") as zf:
        zf.writestr("SFX/Music/Music_Menu.fsb", _fsb_header(5) + b"x" * 100)
    import zlib

    inner = _fsb_header(118) + b"y" * 100
    with zipfile.ZipFile(client / "data" / "Packs" / "SFX_Interface.Mini.pak", "w") as zf:
        zf.writestr("SFX/Interface/Interface.bsb", zlib.compress(inner))
    return client


def test_run_produces_outputs_and_index(tmp_path, fake_vgmstream):
    client = _client_with_paks(tmp_path)
    out_dir = tmp_path / "public" / "game" / "audio"
    index, report = run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)

    assert report == []
    assert set(index) == {"menu", "medals-open"}
    assert index["menu"]["loop"] is True
    assert index["medals-open"]["loop"] is False
    assert index["menu"]["duration"] > 0
    assert (out_dir / "menu.ogg").exists()
    assert (out_dir / "menu.mp3").exists()
    assert (out_dir / "medals-open.ogg").exists()
    assert (out_dir / "medals-open.mp3").exists()
    assert fake_vgmstream["n"] == 2


def test_run_is_idempotent_and_skips_existing_outputs(tmp_path, fake_vgmstream):
    client = _client_with_paks(tmp_path)
    out_dir = tmp_path / "public" / "game" / "audio"
    run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)
    assert fake_vgmstream["n"] == 2

    # Deuxième exécution : rien ne doit être redécodé, l'index doit rester présent.
    index2, report2 = run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)
    assert fake_vgmstream["n"] == 2  # inchangé : aucun nouvel appel à vgmstream
    assert report2 == []
    assert set(index2) == {"menu", "medals-open"}


def test_run_force_reprocesses_existing_outputs(tmp_path, fake_vgmstream):
    client = _client_with_paks(tmp_path)
    out_dir = tmp_path / "public" / "game" / "audio"
    run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)
    assert fake_vgmstream["n"] == 2

    run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=True)
    assert fake_vgmstream["n"] == 4


def test_run_warns_and_continues_on_missing_pak(tmp_path, fake_vgmstream):
    client = tmp_path / "empty_client"
    client.mkdir()
    out_dir = tmp_path / "public" / "game" / "audio"
    index, report = run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)

    assert index == {}
    assert len(report) == 2
    assert all("AVERTISSEMENT" in line for line in report)
    assert fake_vgmstream["n"] == 0


def test_run_warns_on_out_of_range_subsong(tmp_path, fake_vgmstream):
    client = _client_with_paks(tmp_path)
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["tracks"]["menu"]["subsong"] = 99
    out_dir = tmp_path / "public" / "game" / "audio"
    index, report = run(client, manifest, out_dir, Path("/fake/vgmstream-cli"), force=False)

    assert "menu" not in index
    assert any("hors plage" in line for line in report)


def test_run_keeps_previous_index_entry_when_reextraction_fails(tmp_path, fake_vgmstream):
    client = _client_with_paks(tmp_path)
    out_dir = tmp_path / "public" / "game" / "audio"
    index1, _ = run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=False)
    (out_dir.parent / "audio.json").write_text(json.dumps(index1), encoding="utf-8")

    # Le pak disparaît, mais on force une réextraction : l'entrée précédente doit être
    # conservée dans l'index plutôt que d'être perdue.
    shutil.rmtree(client / "data" / "Packs")
    index2, report2 = run(client, MANIFEST, out_dir, Path("/fake/vgmstream-cli"), force=True)

    assert index2["menu"] == index1["menu"]
    assert any("AVERTISSEMENT" in line for line in report2)


# --- test avec le vrai client (sauté si absent) -----------------------------------------

REAL_CLIENT = Path("/mnt/h/MyGames/Allods Online FR (FR)")
REAL_VGMSTREAM = Path(
    "/home/llyam/projects/allods-texts-packer/voices/tools/vgmstream/vgmstream-cli"
)


@pytest.mark.skipif(
    not packs_path(REAL_CLIENT / "data" / "Packs" / "SFX_Music.Mini.pak").exists() or not REAL_VGMSTREAM.exists(),
    reason="client Allods réel ou vgmstream-cli absents de cette machine",
)
def test_run_against_real_client_extracts_menu_track(tmp_path):
    from tools.extract_audio import load_manifest, DEFAULT_MANIFEST

    manifest = load_manifest(DEFAULT_MANIFEST)
    out_dir = tmp_path / "audio"
    index, report = run(REAL_CLIENT, manifest, out_dir, REAL_VGMSTREAM, force=False)
    assert "menu" in index
    assert index["menu"]["duration"] > 60
    assert (out_dir / "menu.ogg").exists()
    assert (out_dir / "menu.mp3").exists()
