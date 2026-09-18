import io, os, struct, zipfile, zlib
from PIL import Image
import pytest

from tools.uitexture import candidate_dims, build_dds, decode_uitexture, row_smoothness


def test_candidate_dims_lists_power_of_two_pairs():
    # 2048 blocs DXT5 → 32768 px : 256x128, 128x256, 512x64...
    dims = candidate_dims(2048)
    assert (256, 128) in dims and (128, 256) in dims
    assert all((w // 4) * (h // 4) == 2048 for w, h in dims)
    assert (2048, 16) not in candidate_dims(2048, max_ratio=16)  # ratio 128 exclu


def test_build_dds_header_is_128_bytes_plus_payload():
    payload = b"\0" * 16
    dds = build_dds(4, 4, b"DXT5", payload)
    assert dds[:4] == b"DDS " and len(dds) == 128 + 16
    height, width = struct.unpack("<II", dds[12:20])
    assert (width, height) == (4, 4)


def _dxt1_solid_block(r: int, g: int, b: int) -> bytes:
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return struct.pack("<HHI", c, c, 0)  # deux couleurs identiques, indices 0


def _make_uitexture(width: int, height: int, blocks: bytes) -> bytes:
    return zlib.compress(struct.pack("<II", 0, len(blocks)) + blocks)


def test_decode_solid_dxt1_texture_with_hint():
    blocks = _dxt1_solid_block(255, 0, 0) * (4 * 2)  # 16x8
    img, info = decode_uitexture(_make_uitexture(16, 8, blocks), dims_hint=(16, 8))
    assert (info.width, info.height, info.fourcc) == (16, 8, "DXT1")
    assert img.getpixel((0, 0))[:3] == (255, 0, 0)


def test_decode_infers_dims_from_gradient():
    # Dégradé horizontal 64x16 en DXT1 : la bonne largeur donne des lignes identiques.
    blocks = b"".join(_dxt1_solid_block(x * 16, 0, 0) for _y in range(4) for x in range(16))
    img, info = decode_uitexture(_make_uitexture(64, 16, blocks))
    assert (info.width, info.height) == (64, 16)
    assert row_smoothness(img) == 0.0


CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")


@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_medal_frame():
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Ingame/Medals/Textures/MedalFrame100.(UITexture).bin")
    img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (128, 256, "DXT5")
    assert img.getpixel((0, 0))[3] == 0  # coin transparent
