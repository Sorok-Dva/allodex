import os, struct, zipfile, zlib
import pytest

from tools.uitexture import candidate_dims, build_dds, decode_uitexture, row_smoothness, _is_better


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
    # Dégradé horizontal 64x16 en DXT1 : la bonne largeur donne des lignes identiques
    # (composante verticale du score nulle) et un dégradé continu par colonne. La
    # mauvaise largeur (128, 8) replie le même flux d'octets en deux passages du
    # dégradé sur une même ligne, ce qui introduit une rupture brutale (240 → 0) et
    # alourdit son score (composante horizontale) : (64, 16) l'emporte désormais sur
    # le score seul, sans même recourir au départage forme carrée/paysage.
    blocks = b"".join(_dxt1_solid_block(x * 16, 0, 0) for _y in range(4) for x in range(16))
    img, info = decode_uitexture(_make_uitexture(64, 16, blocks))
    assert (info.width, info.height) == (64, 16)
    assert row_smoothness(img) < 1.0  # lignes identiques, dégradé continu par colonne : score bas
    assert img.getpixel((0, 0))[0] < 40  # début du dégradé (rouge ≈ 0)
    assert img.getpixel((63, 0))[0] > 200  # fin du dégradé (rouge ≈ 240)


def test_tie_break_prefers_squarest_when_scores_equal():
    # À score égal, (16, 16) (carré, ratio 1) doit l'emporter sur (64, 4) (ratio 16).
    assert _is_better(0.0, 16, 16, 0.0, 64, 4) is True
    # Et l'inverse ne doit pas remplacer un carré déjà trouvé.
    assert _is_better(0.0, 64, 4, 0.0, 16, 16) is False


def test_tie_break_prefers_landscape_when_shape_also_tied():
    # Même score, même ratio (4) : le format paysage (32, 8) l'emporte sur (8, 32).
    assert _is_better(0.0, 32, 8, 0.0, 8, 32) is True
    assert _is_better(0.0, 8, 32, 0.0, 32, 8) is False


def test_tie_break_score_still_takes_priority_over_shape():
    # Un score strictement meilleur l'emporte même si la forme est moins carrée.
    assert _is_better(0.0, 64, 4, 1.0, 16, 16) is True
    assert _is_better(1.0, 16, 16, 0.0, 64, 4) is False


CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")


@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_medal_frame():
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Ingame/Medals/Textures/MedalFrame100.(UITexture).bin")
    img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (128, 256, "DXT5")
    assert img.getpixel((0, 0))[3] == 0  # coin transparent


@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_gold_medal_is_dxt1_not_dxt5():
    # Régression : l'ancien score (niveaux de gris, lignes seules) laissait un
    # DXT1 relu en DXT5 (32x64, image bruitée) l'emporter à tort sur le vrai
    # DXT1 64x64 (icône nette).
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin")
    _img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (64, 64, "DXT1")


@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_diamond_medal_is_genuinely_dxt5():
    # Contre-exemple : celle-ci est réellement en 32x64 DXT5, le nouveau score ne
    # doit pas la faire basculer à tort vers un DXT1.
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Icons/Special/Currency/DiamondMedal.(UITexture).bin")
    _img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (32, 64, "DXT5")


@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_button_login_normal_without_hint():
    # Cette texture nécessitait un dims_hint (256, 256) avant la correction du
    # score ; elle doit maintenant s'inférer correctement sans indice.
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Wrap/MainMenu/LoginAccount/ButtonLoginNormal.(UITexture).bin")
    _img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (256, 256, "DXT5")
