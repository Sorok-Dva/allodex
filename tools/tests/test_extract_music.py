import json
from pathlib import Path
import zipfile

from tools import extract_music as music


def test_slugs_are_safe_stable_and_distinct():
    assert music.slug("../AC5_Main_NM.wav").startswith("ac5-main-nm-")
    assert music.slug("A_B") != music.slug("A-B")
    assert music.slug("A_B") == music.slug("A_B")
    assert "/" not in music.slug("../../")


def setup_clients(tmp_path, monkeypatch):
    clients = []
    for ident in ("16.0", "17.0"):
        root = tmp_path / ident
        root.mkdir()
        with zipfile.ZipFile(root / "music.pak", "w") as z:
            z.writestr("SFX/Music/Music_Menu.fsb", b"FSB5fake")
            z.writestr("SFX/Music/Music_Zone.fsb", b"FSB5fake")
        clients.append(dict(id=ident, root=str(root), pak="music.pak"))
    calls = []
    monkeypatch.setattr(music, "list_subsongs", lambda *args: [dict(index=1, name="Main_NM.wav", duration=12)])
    monkeypatch.setattr(music, "decode_subsong", lambda *args: calls.append(args))
    monkeypatch.setattr(music, "fold_to_stereo", lambda wav: wav)
    def encode(wav, base, category):
        assert category == "tracks"
        for ext in (".ogg", ".mp3"):
            base.with_suffix(ext).write_bytes(b"encoded")
    monkeypatch.setattr(music, "encode_outputs", encode)
    monkeypatch.setattr(music, "probe_duration", lambda wav: 12.25)
    return dict(clients=clients, banks={"Music_Menu": "Menu", "Music_Zone": "Zones"}), calls


def test_deduplication_metadata_and_idempotency(tmp_path, monkeypatch):
    manifest, calls = setup_clients(tmp_path, monkeypatch)
    out = tmp_path / "game/music"
    titles = {"Main_NM": {"fr": "Thème", "en": "Theme"}}
    index, warnings = music.run(manifest, titles, out)
    assert not warnings
    assert len(index) == len(calls) == 1
    assert index[0]["client"] == "16.0"
    assert index[0]["group"] == "Menu"
    assert index[0]["duration"] == 12.25
    assert index[0]["title"] == titles["Main_NM"]
    assert json.loads((out.parent / "music.json").read_text()) == index
    music.run(manifest, titles, out)
    assert len(calls) == 1
    music.run(manifest, titles, out, force=True)
    assert len(calls) == 2


def test_only_and_missing_clients_keep_existing_tracks(tmp_path, monkeypatch):
    manifest, calls = setup_clients(tmp_path, monkeypatch)
    out = tmp_path / "game/music"
    original, _ = music.run(manifest, {}, out)
    monkeypatch.setattr(music, "list_subsongs", lambda *args: [dict(index=1, name="Zone", duration=12)])
    index, _ = music.run(manifest, {}, out, only="Music_Zone")
    assert [e["group"] for e in index] == ["Menu", "Zones"]
    assert index[0] == original[0]
    for client in manifest["clients"]:
        client["root"] += "/absent"
    preserved, warnings = music.run(manifest, {}, out)
    assert preserved == index
    assert len(warnings) == 2


def test_failed_track_does_not_stop_following_tracks(tmp_path, monkeypatch):
    manifest, calls = setup_clients(tmp_path, monkeypatch)
    monkeypatch.setattr(music, "list_subsongs", lambda *args: [
        dict(index=1, name="Broken", duration=12), dict(index=2, name="Good", duration=12)])
    def decode(*args):
        if args[3] == 1:
            raise RuntimeError("decode failed")
    monkeypatch.setattr(music, "decode_subsong", decode)
    index, warnings = music.run(manifest, {}, tmp_path / "game/music")
    assert [e["name"] for e in index] == ["Good"]
    assert len(warnings) == 1
