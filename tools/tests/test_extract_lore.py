import json
import struct
import zipfile
import zlib

import pytest

from tools import extract_lore as lore


# --- fabrique de données synthétiques ------------------------------------------------------------

def build_pack(resources: dict[int, int], keys: dict[int, int], body: bytes, fingerprint=0x5E102AA3,
               buckets: int = 5) -> bytes:
    """`pack.bin` décompressé minimal : en-tête, S0 (rid → décalage), S3 (resourceId → décalage), corps."""
    header_len = 0x50
    out = bytearray(header_len)
    s0_base = len(out)
    out += bytes(buckets * 8)
    s0 = [[] for _ in range(buckets)]
    for rid, off in resources.items():
        s0[rid % buckets].append((rid, off))
    for b, items in enumerate(s0):
        items_at = len(out)
        struct.pack_into("<II", out, s0_base + b * 8, items_at - (s0_base + b * 8), len(items))
        out += bytes(len(items) * 16)
        for k, (rid, off) in enumerate(items):
            key_at = len(out)
            out += struct.pack("<II", 1, rid) + b"\0" + bytes(7)
            io = items_at + k * 16
            struct.pack_into("<IIQ", out, io, key_at - io, 9, off)
    s3_base = len(out)
    out += bytes(buckets * 8)
    s3 = [[] for _ in range(buckets)]
    for key, off in keys.items():
        s3[key % buckets].append((key, off))
    for b, items in enumerate(s3):
        items_at = len(out)
        struct.pack_into("<II", out, s3_base + b * 8, items_at - (s3_base + b * 8), len(items))
        for key, off in items:
            out += struct.pack("<QQ", key, off)
    out += bytes(-len(out) % 8)
    body_start = len(out)
    struct.pack_into("<IIIIQ", out, 0, 0x592E02CC, 1139, fingerprint, 2, body_start)
    struct.pack_into("<II", out, 0x18, s0_base - 0x18, buckets)
    struct.pack_into("<II", out, 0x30, s3_base - 0x30, buckets)
    return bytes(out) + body


def with_relocs(pack: bytes, pairs: list[tuple[int, int, int]]) -> bytes:
    """Ajoute la table de relocation : `u64 N` puis N × `(u64 emplacement | étiquette, u64 cible)`."""
    out = bytearray(pack) + bytes(-len(pack) % 8)
    out += struct.pack("<Q", len(pairs))
    for loc, tag, target in pairs:
        out += struct.pack("<QQ", loc | tag, target)
    return bytes(out)


def secrets_body(quest_offset: int, ws: int, texts: dict[str, int]) -> tuple[bytes, list, int]:
    """WorldSecrets (1 secret, 1 étape) à `ws`, suivi de la ressource du secret → (octets, relocations,
    décalage du secret). Disposition : voir `extract_lore.find_secrets`."""
    items, comps = ws + 72, ws + 128
    path, secret = comps + 120, ws + 288
    b = bytearray(288)
    struct.pack_into("<I", b, 84, 56)                               # tableau secrets : 1 élément
    struct.pack_into("<I", b, 72 + 52, 120)                         # tableau components : 1 étape
    struct.pack_into("<II", b, 128 + 76, texts["not_ready"], 0)
    struct.pack_into("<I", b, 128 + 92, 8)                          # path : 1 quête
    struct.pack_into("<II", b, 128 + 148, texts["text"], 0)
    sec = resource(700, {460: texts["name"], 260: texts["description"]})
    relocs = [(ws + 40, 3, items), (items + 8, 3, comps), (items + 48, 0, secret), (comps + 48, 3, path),
              (comps + 80, 0, quest_offset), (comps + 8, 0, quest_offset), (path, 0, quest_offset)]
    return bytes(b) + sec, relocs, secret


def resource(size: int, refs: dict[int, int]) -> bytes:
    """Ressource de `size` octets portant les index de textes `refs` ({décalage: index})."""
    b = bytearray(size)
    for rel, idx in refs.items():
        struct.pack_into("<II", b, rel, idx, 0)
    return bytes(b)


# --- .loc et rendu ------------------------------------------------------------------------------

def test_loc_roundtrip_keeps_order_empty_strings_and_fingerprint():
    texts = ["Кассандра", "", "<html>Hello<br/>world</html>", "é" * 7]
    fp, parsed = lore.parse_loc(lore.build_loc(texts, fingerprint=0x1234))
    assert fp == 0x1234 and parsed == texts
    fp2, parsed2 = lore.parse_loc(zlib.decompress(lore.build_loc(texts)))   # non compressé aussi
    assert parsed2 == texts


def test_parse_loc_rejects_garbage():
    with pytest.raises((ValueError, struct.error)):
        lore.parse_loc(struct.pack("<IIQ", 1, 0, 4) + b"\0" * 8)


def test_render_resolves_little_endian_hrefs_and_converts_markup():
    texts = ["Demon of Fear", '<html>Path <t href="0000000000000000"/> – <r name="level"/><br/>end&amp;co</html>',
             '<t href="0200000000000000"/>']
    assert lore.href_index("0200000000000000") == 2
    assert lore.href_index("620a020000000000") == 0x020A62
    assert lore.render(1, texts) == "Path Demon of Fear – {level}\nend&co"
    assert lore.render(2, texts) == ""          # auto-référence : pas de boucle infinie


def test_en_status_distinguishes_official_partial_missing():
    assert lore.en_status("Hello", "Hello") == "official"
    assert lore.en_status('Hi <t href="01"/>', "Hi Привет") == "partial"
    assert lore.en_status("Привет", "Привет") == "missing"
    assert lore.en_status("", "") == "missing"


def test_norm_key_ignores_build_specific_hrefs():
    assert lore.norm_key('A <t href="0100000000000000"/>\r\n') == lore.norm_key('A <t href="/Items/X.txt"/>\n')


# --- pack.bin ------------------------------------------------------------------------------------

def test_parse_pack_reads_resource_and_resource_id_tables():
    body = resource(64, {}) + resource(32, {})
    raw = build_pack({5: 0, 9: 64}, {777: 0}, body)
    idx = lore.parse_pack(raw)
    assert idx.fingerprint == 0x5E102AA3
    assert idx.rid_offset == {5: 0, 9: 64} and idx.key_offset == {777: 0}
    assert raw[idx.body:] == body
    assert list(idx.sizes) == [64, 32] and idx.offset_key[0] == 777


def test_text_owner_is_the_resource_whose_texts_are_neighbours():
    quest = resource(64, {8: 1000, 16: 1001, 24: 1002})
    other = resource(64, {8: 1002, 40: 5000})            # référence isolée (fausse ou simple renvoi)
    raw = build_pack({1: 0, 2: 64}, {}, quest + other)
    idx = lore.parse_pack(raw)
    refs = lore.scan_refs(raw, idx, n_texts=6000)
    sup = lore.support(refs)
    owners = lore.pick_owners(refs, sup, {1: 64, 2: 64})
    assert owners[1000][0] == 1 and owners[1002][0] == 1 and owners[1002][2] == 24
    assert owners[5000][0] == 2 and owners[5000][1] == 0


def test_scan_refs_skips_small_values_and_huge_regions():
    raw = build_pack({1: 0}, {}, resource(64, {8: 12, 16: 400}))
    idx = lore.parse_pack(raw)
    refs = lore.scan_refs(raw, idx, n_texts=1000)
    assert list(refs["val"]) == [400]
    assert len(lore.scan_refs(raw, idx, n_texts=1000, max_region=10)["val"]) == 0


def test_layout_classifier_learns_text_offsets():
    shape = (0,) * 8
    samples = [(lore.LayoutClassifier.features([260, 460, 636], shape), "QuestResource")] * 5 + \
              [(lore.LayoutClassifier.features([372, 588], shape), "ItemResource")] * 5
    clf = lore.LayoutClassifier().fit(samples)
    assert clf.predict(lore.LayoutClassifier.features([260, 460], shape))[0] == "QuestResource"
    label, conf = clf.predict(lore.LayoutClassifier.features([588], shape))
    assert label == "ItemResource" and conf > 0.9
    assert clf.predict(lore.LayoutClassifier.features([12], shape)) == (None, 0.0)


def test_xdb_text_refs_resolves_relative_and_absolute_hrefs():
    xdb = b'''<?xml version="1.0" encoding="UTF-8" ?>
<gameMechanics.constructor.schemes.quest.QuestResource>
  <Header><resourceId>42</resourceId></Header>
  <name href="Name.txt" />
  <counters><Item><customName href="/World/Other/C.txt#xpointer(x)" /></Item></counters>
</gameMechanics.constructor.schemes.quest.QuestResource>'''
    root, rid, refs = lore.xdb_text_refs("World/Quests/Q1/Q1.xdb", xdb)
    assert root == "gameMechanics.constructor.schemes.quest.QuestResource" and rid == 42
    assert refs == [("World/Quests/Q1/Name.txt", "name"), ("World/Other/C.txt", "counters/Item/customName")]


# --- catégories -----------------------------------------------------------------------------------

def test_documents_flavor_and_mechanics_items():
    page = ("<html>Так начнем повесть сию. " + "Древен народ канийский и славен делами. " * 6
            + "<br/><tip_grey>Загляните в «Летопись Валиров»</tip_grey></html>")
    assert lore.is_document("Страница первая «Летописи Валиров»", page) == "document"
    assert lore.is_document("Ржаной каравай", "Горячий хлеб, душистый и тяжёлый. " * 7) == "flavor"
    assert lore.is_document("Набор героя", "Содержит следующие бонусы: " + "руны; " * 50) is None
    assert lore.is_document("Письмо", "Коротко.") is None


def test_series_keys():
    assert lore.book_key("Страница первая «Летописи Валиров». Откуда есть пошла") == "Летописи Валиров"
    assert lore.book_key("Дневник Лары Лопатиной, страница от 29 июня 1018 года") == "Дневник Лары Лопатиной"
    assert lore.book_key("Восьмая записка кентавра-путешественника") == "Записка кентавра-путешественника"
    assert lore.book_key("Ржаной каравай") is None


# --- corpus communautaire ------------------------------------------------------------------------

def test_sentence_units_and_coverage():
    text = "Короткая.\nЭто достаточно длинная фраза из игры про Сарнаут. Ещё одна фраза, которой нет в игре вовсе!"
    units = lore.sentences(text)
    assert units == ["это достаточно длинная фраза из игры про сарнаут", "еще одна фраза которой нет в игре вовсе"]
    index = {units[0]: [7]}
    cov, share, locs = lore.coverage_of(units, index, lambda t: True)
    assert 0.4 < cov < 0.7 and share == 1.0 and locs == {7: 1}
    assert lore.short_lines("[/Maps/X/Zone.txt]: Остров Буян\nодно") == ["maps x zone txt остров буян"]
    assert lore.clean_corpus_text("[/Maps/X/Zone.txt]: <html>Остров Буян</html>").strip() == "Остров Буян"


def test_classify_community_rules():
    prov = {"excluded": {"patterns": ["текстовик"]}, "official": {"patterns": ["анонс"]},
            "community": {"patterns": ["хронология"]},
            "files": {"x/story.txt": {"class": "community", "note": "verify"}}}
    assert lore.classify_community("текстовик/pack.txt", 0.99, 1.0, prov)[0].startswith("excluded")
    assert lore.classify_community("a.txt", 0.9, 0.9, prov)[0] == "in-game (official EN available)"
    assert lore.classify_community("a.txt", 0.9, 0.2, prov)[0] == "in-game (RU/FR only)"
    assert lore.classify_community("Кадаган/анонс.txt", 0.0, 0.0, prov)[0].startswith("official")
    assert lore.classify_community("хронология.txt", 0.0, 0.0, prov)[0] == "community"
    assert lore.classify_community("x/story.txt", 0.1, 0.0, prov) == ("community", "verify")
    assert lore.classify_community("post.txt", 0.0, 0.0, prov, "Тени над Шлегерлогтом10.04.2026 …")[0].startswith("official")


def test_credit_source_first_pattern_then_default_for_community():
    credit = {"sources": [{"patterns": ["АТЛАС"], "source": "atlas"}], "default_source": "author"}
    assert lore.credit_source("x/АТЛАС АЛЛОДЫ.xlsx", lore.CLASSES[4], credit) == "atlas"
    assert lore.credit_source("рассказ.txt", lore.CLASSES[3], credit) == "author"
    assert lore.credit_source("анонс.txt", lore.CLASSES[2], credit) is None
    assert lore.credit_source("рассказ.txt", lore.CLASSES[3], {}) is None


def test_atlas_and_glossary_name_helpers():
    assert lore.atlas_base_name("Айрин (Умойр)") == ("Айрин", "Умойр")
    assert lore.atlas_base_name("Аммра") == ("Аммра", None)
    assert lore.norm_name("«Остров Мёртвых»") == "остров мертвых"


def test_bridge_fr_keeps_the_local_majority_offset_and_fills_gaps():
    # 17.0 : textes 1000..1011 ; client FR : même ordre, décalé de 5 (textes ajoutés en 17.0)
    ru = [""] * 1000 + [f"Текст {i}" for i in range(12)]
    fr = [""] * 995 + [f"Texte {i}" for i in range(12)]
    ru_owner, fr_owner, ru_key, fr_key = {}, {}, {}, {}
    for i in range(12):
        ru_owner[1000 + i] = (100 + i, 1, 8)
        ru_key[100 + i] = 9000 + i
    for i in (0, 1, 2, 3, 5, 7, 8, 9, 10, 11):          # 4 et 6 : ressource absente du client FR
        fr_owner[995 + i] = (200 + i, 1, 8)
        fr_key[200 + i] = 9000 + i
    fr_owner[995 + 5], fr_owner[995 + 9] = (200 + 9, 1, 8), (200 + 5, 1, 8)   # 5 et 9 permutés (révision)
    fr_owner[1003] = (200 + 3, 1, 8)                    # t == j : entier identique, pas une référence
    ru_owner[1003] = (100 + 3, 1, 8)
    match = lore.bridge_fr(ru_owner, ru_key, fr_owner, fr_key, ru, fr)
    assert match[1000] == (995, "resource") and match[1011] == (1006, "resource")
    assert match[1004] == (999, "offset") and match[1006] == (1001, "offset")      # comblés entre ancres
    assert match[1005] == (1000, "offset") and match[1009] == (1004, "offset")     # permutation écartée
    assert all(j == t - 5 for t, (j, _) in match.items())


def test_apply_overrides_prefers_option_then_environment():
    m = {"client": {"root": "/a"}, "fr_client": {"root": "/fr"}, "server_root": "/s"}
    out = lore.apply_overrides(m, {"fr_client": "/opt/fr"}, {"ALLODS_RU_CLIENT_DIR": "/env/ru", "ALLODS_FR_CLIENT_DIR": "/env/fr"})
    assert out["client"]["root"] == "/env/ru" and out["fr_client"]["root"] == "/opt/fr" and out["server_root"] == "/s"
    assert lore.apply_overrides(m, {}, {"ALLODS_CLIENT_DIR": "/c"})["fr_client"]["root"] == "/c"
    assert m["fr_client"]["root"] == "/fr"                                          # manifeste intact


def test_split_languages_keeps_secret_quest_links():
    entries = [{"id": "r8", "fields": {}, "components": [{"text": {"loc": 7, "ru": "Шаг", "en": "Step"},
                                                          "quests": {"start": "r5", "final": None, "path": ["r5"]}}]}]
    main, ru, fr = lore.split_languages(entries)
    assert main[0]["components"][0] == {"text": {"loc": 7, "en": "Step"}, "quests": {"start": "r5", "final": None, "path": ["r5"]}}
    assert ru == {"7": "Шаг"} and [f["loc"] for f in lore.entry_texts(entries[0])] == [7]


def test_split_languages_moves_ru_and_fr_out_of_the_main_file():
    entries = [{"id": "r1", "fields": {"name": {"loc": 5, "ru": "Имя", "en": "Name", "fr": "Nom", "en_status": "official"}}}]
    main, ru, fr = lore.split_languages(entries)
    assert main[0]["fields"]["name"] == {"loc": 5, "en": "Name", "en_status": "official", "fr": True}
    assert ru == {"5": "Имя"} and fr == {"5": "Nom"}
    assert entries[0]["fields"]["name"]["ru"] == "Имя"     # l'entrée d'origine n'est pas modifiée


# --- bout en bout -----------------------------------------------------------------------------------

def utf16(s: str) -> bytes:
    return b"\xff\xfe" + s.encode("utf-16le")


START_RU = "Слушай внимательно, герой: демоны снова вышли из астрала у старой башни."


def make_sources(tmp_path) -> dict:
    """Client 17.0 synthétique (paks), arbre serveur (xdb + txt) et corpus → manifeste."""
    ru = [f"Филлер {i}" for i in range(400)]
    en = [f"Filler {i}" for i in range(400)]
    start_ru = START_RU
    ru[310], en[310] = "Волчья угроза", "Wolf Threat"
    ru[311], en[311] = "Убить четырёх волков.", "Kill four wolves."
    ru[312], en[312] = start_ru, "Listen carefully, hero: demons came out of the Astral again."
    ru[320], en[320] = "Смеяна", "Catherina"
    ru[321], en[321] = "Княжна Кании", "Princess of Kania"
    ru[330], en[330] = "Тайна раскрыта: камень джунов ведёт к древним порталам.", "The June stone leads to ancient portals."
    ru[331], en[331] = "Этот этап Тайны Мира начинается у Селены.", "This stage starts with Selene."
    ru[332], en[332] = "Древняя магия джунов", "Ancient June Magic"
    ru[333], en[333] = "Странный камень отыскала Аманда.", "Amanda found a strange stone."
    client = tmp_path / "client"
    (client / "data/Packs").mkdir(parents=True)
    (client / "Profiles").mkdir()
    (client / "Profiles/game.version").write_bytes(b"ver5\t17.0.01.64\x00")
    with zipfile.ZipFile(client / "data/Packs/Texts_x64.pak", "w") as z:
        z.writestr("Bin/pack.rus.loc", lore.build_loc(ru))
        z.writestr("Bin/pack.eng_eu.loc", lore.build_loc(en))
    body = resource(64, {8: 310, 16: 311, 24: 312}) + resource(64, {8: 320, 16: 321})
    sec, relocs, sec_off = secrets_body(0, len(body), {"text": 330, "not_ready": 331, "name": 332, "description": 333})
    pack = build_pack({5: 0, 6: 64, 7: len(body), 8: sec_off}, {123456: 0, 654321: 64, lore.WORLD_SECRETS_ID: len(body)},
                      body + sec)
    with zipfile.ZipFile(client / "data/Packs/BaseLocall_x64.pak", "w") as z:
        z.writestr("Bin/pack.bin", zlib.compress(with_relocs(pack, relocs)))
    # client FR 16.0 : mêmes ressources (resourceId), textes décalés de 5 index, français seul
    fr = [f"Remplissage {i}" for i in range(395)]
    fr[305], fr[306] = "Menace des loups", "Tuer quatre loups."
    fr[307] = "Écoutez bien, héros : les démons sont de nouveau sortis de l'Astral."
    fr[315], fr[316] = "Catherina", "Princesse de Kania"
    fr_client = tmp_path / "fr_client"
    (fr_client / "data/Packs").mkdir(parents=True)
    with zipfile.ZipFile(fr_client / "data/Packs/Texts_x64.pak", "w") as z:
        z.writestr("Bin/pack.loc", lore.build_loc(fr))
    fr_pack = build_pack({15: 0, 16: 64}, {123456: 0, 654321: 64},
                         resource(64, {8: 305, 16: 306, 24: 307}) + resource(64, {8: 315, 16: 316}))
    with zipfile.ZipFile(fr_client / "data/Packs/BaseLocfra_x64.pak", "w") as z:
        z.writestr("Bin/pack.bin", zlib.compress(fr_pack))
    server = tmp_path / "server"
    q = server / "World/Quests/Q1"
    q.mkdir(parents=True)
    (q / "Q1.xdb").write_text('<?xml version="1.0" encoding="UTF-8" ?>\n<gameMechanics.constructor.schemes.quest.QuestResource>'
                              '<Header><resourceId>123456</resourceId></Header><name href="Name.txt" />'
                              '<goal href="Goal.txt" /><startText href="/World/Quests/Q1/Start.txt" />'
                              '</gameMechanics.constructor.schemes.quest.QuestResource>')
    (q / "Name.txt").write_bytes(utf16(ru[310]))
    (q / "Goal.txt").write_bytes(utf16(ru[311]))
    (q / "Start.txt").write_bytes(utf16(start_ru))
    m = server / "Characters/NPC"
    m.mkdir(parents=True)
    (m / "Smeyana.(MobWorld).xdb").write_text('<?xml version="1.0" encoding="UTF-8" ?>\n<gameMechanics.world.mob.MobWorld>'
                                              '<Header><resourceId>654321</resourceId></Header><name href="N.txt" />'
                                              '<title href="T.txt" /></gameMechanics.world.mob.MobWorld>')
    (m / "N.txt").write_bytes(utf16(ru[320]))
    (m / "T.txt").write_bytes(utf16(ru[321]))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "сказ.txt").write_text(start_ru + "\n", encoding="utf-8")
    (corpus / "анонс.txt").write_text("Скоро в игре новая глава о демонах астрала и древних башнях.", encoding="utf-8")
    manifest = {"client": {"root": str(client), "texts_pak": "data/Packs/Texts_x64.pak",
                           "base_pak": "data/Packs/BaseLocall_x64.pak", "ru": "Bin/pack.rus.loc",
                           "en": "Bin/pack.eng_eu.loc", "pack": "Bin/pack.bin"},
                "fr_client": {"root": str(fr_client), "texts_pak": "data/Packs/Texts_x64.pak", "member": "Bin/pack.loc",
                              "base_pak": "data/Packs/BaseLocfra_x64.pak", "pack": "Bin/pack.bin"},
                "server_root": str(server), "corpus": str(corpus),
                "provenance": {"official": {"patterns": ["анонс"]}},
                "credit": {"short": "M. T.", "line": "Atlas: M. T.", "default_source": "supplied by the author",
                           "sources": [{"patterns": ["сказ"], "source": "story"}]}}
    return manifest


def test_end_to_end_quest_from_synthetic_client_server_and_corpus(tmp_path):
    manifest = make_sources(tmp_path)
    start_ru = START_RU
    out = tmp_path / "lore"
    index = lore.Extractor(manifest, out, log=lambda *a: None).run()
    quests = json.loads((out / "quests.json").read_text(encoding="utf-8"))
    assert len(quests) == 1
    qe = quests[0]
    assert qe["type"] == "QuestResource" and qe["type_source"] == "server" and qe["era"] == "legacy"
    assert qe["path"] == "World/Quests/Q1/Q1.xdb" and qe["resource_id"] == 123456
    assert set(qe["fields"]) == {"name", "goal", "startText"}
    assert qe["fields"]["name"] == {"loc": 310, "en_status": "official", "en": "Wolf Threat", "fr": True}
    assert json.loads((out / "ru/quests.json").read_text(encoding="utf-8"))["312"] == start_ru
    assert json.loads((out / "fr/quests.json").read_text(encoding="utf-8"))["310"] == "Menace des loups"
    # 5 textes par ressource commune, 7 comblés entre les ancres 312 et 320 (même écart)
    assert index["fr"]["by_method"] == {"resource": 5, "offset": 7}
    secrets = json.loads((out / "secrets.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in secrets] == ["r8"] and secrets[0]["type_source"] == "relocation"
    assert secrets[0]["fields"]["name"]["en"] == "Ancient June Magic"
    step = secrets[0]["components"][0]
    assert step["text"]["loc"] == 330 and step["not_ready"]["loc"] == 331
    assert step["quests"] == {"start": "r5", "final": "r5", "path": ["r5"]}
    assert json.loads((out / "ru/secrets.json").read_text(encoding="utf-8"))["330"].startswith("Тайна раскрыта")
    chars = json.loads((out / "characters.json").read_text(encoding="utf-8"))
    assert chars[0]["fields"]["name"]["en"] == "Catherina"
    glossary = json.loads((out / "glossary.json").read_text(encoding="utf-8"))
    assert {"ru": "Смеяна", "en": "Catherina"}.items() <= glossary[0].items()
    community = json.loads((out / "community.json").read_text(encoding="utf-8"))
    assert community["credit"] == {"short": "M. T.", "line": "Atlas: M. T."}
    files = {c["path"]: c for c in community["files"]}
    assert files["сказ.txt"]["class"] == "in-game (official EN available)" and files["сказ.txt"]["loc"] == [312]
    assert files["анонс.txt"]["class"].startswith("official") and "credit" not in files["анонс.txt"]
    assert (files["сказ.txt"]["credit"], files["сказ.txt"]["source"]) == ("M. T.", "story")
    assert index["client"]["version"] == "17.0.01.64" and index["stats"]["quests"]["en_texts"] == 3
    assert index["notes"] == []


def test_without_fr_client_french_is_skipped_and_reported(tmp_path):
    manifest = make_sources(tmp_path)
    manifest["fr_client"]["root"] = str(tmp_path / "absent")
    index = lore.Extractor(manifest, tmp_path / "lore", log=lambda *a: None).run()
    assert index["fr"] == {} and any("client FR absent" in n for n in index["notes"])
    assert not (tmp_path / "lore" / "fr").exists()


def test_without_server_tree_types_stay_unknown_and_the_gap_is_reported(tmp_path):
    manifest = make_sources(tmp_path)
    manifest["server_root"] = str(tmp_path / "absent")
    out = tmp_path / "lore"
    index = lore.Extractor(manifest, out, log=lambda *a: None).run()
    assert not (out / "quests.json").exists()
    assert any("arbre serveur absent" in n for n in index["notes"])
    assert (out / "secrets.json").exists()                  # secrets résolus sans l'arbre (relocations)
    community = {c["path"]: c for c in json.loads((out / "community.json").read_text(encoding="utf-8"))["files"]}
    assert community["сказ.txt"]["class"] == "in-game (official EN available)"   # l'appariement reste possible
