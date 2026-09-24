import json

import numpy as np

from tools import build_lorebook as lb
from tools import extract_lore as lore


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def rec(loc, en=None, revised=False):
    r = {"loc": loc, "en_status": "official" if en else "missing"}
    if en:
        r["en"] = en
    if revised:
        r["ru_revised"] = True
    return r


def make_lore(tmp_path):
    """Extraction minimale : une quête liée à un secret et à un PNJ, un PNJ avec sa réplique, un lieu."""
    root = tmp_path / "lore"
    write(root / "quests.json", [{"id": "r10", "type": "QuestResource", "era": "legacy",
                                  "path": "World/Quests/Kania/Q1/Q1.xdb",
                                  "fields": {"name": rec(1000, "Wolf Threat"), "goal": rec(1001),
                                             "startText": rec(1002, "Listen, hero.", revised=True)}}])
    write(root / "characters.json", [{"id": "r20", "type": "MobWorld", "era": "legacy",
                                      "path": "Characters/Kania_female/Instances/Kania/Smeyana.xdb",
                                      "fields": {"name": rec(1100, "Catherina"), "title": rec(1101, "Princess")}}])
    write(root / "dialogues.json", [{"id": "r30", "type": "Cue", "fields": {"name": rec(1200, "Who are you?"),
                                                                             "text": rec(1201, "I am Catherina of Kania.")}},
                                    {"id": "r31", "type": "Cue", "fields": {"text": rec(1202, "The wolves are coming back.")}}])
    write(root / "places.json", [{"id": "r40", "type": "ZoneResource", "path": "Maps/Kania/Kania.(ZoneResource).xdb",
                                  "fields": {"name": rec(1300, "Kania")}}])
    write(root / "secrets.json", [{"id": "r50", "type": "WorldSecret", "order": 0,
                                   "fields": {"name": rec(1400, "Ancient June Magic")},
                                   "components": [{"text": rec(1401, "The stone is solved."), "not_ready": rec(1402),
                                                   "quests": {"start": "r10", "final": "r10", "path": ["r10"]}}]}])
    write(root / "ru" / "all.json", {"1000": "Волчья угроза", "1001": "Убить волков.", "1002": "Слушай, герой.",
                                     "1100": "Смеяна", "1101": "Княжна", "1200": "Кто ты?", "1201": "Я Смеяна.",
                                     "1300": "Кания", "1400": "Древняя магия джунов", "1401": "Тайна раскрыта.",
                                     "1402": "Начните у Селены.", "1202": "Волки возвращаются."})
    write(root / "fr" / "all.json", {"1001": "Tuez les loups.", "1100": "Catherina", "1402": "Commencez chez Séléné."})
    write(root / "links.json", {"dialogue_character": {"r30": "r20"}, "dialogue_quest": {"r31": "r10"},
                                "quest_characters": {"r10": ["r20"]}})
    write(root / "community.json", {"credit": {"line": "Atlas: M. T.", "short": "M. T.", "url": "https://example.org"},
                                    "files": []})
    src = tmp_path / "src"
    (src / "community").mkdir(parents=True)
    (src / "community" / "memories.md").write_text(
        "---\nid: c-memories\ntitle: Memories of Catherina\ntitle_ru: Воспоминания Смеяны\n"
        "source: stories/memories.txt\nkind: story\n---\n## 13 March\n\nI was born into a family of rulers.\n",
        encoding="utf-8")
    write(src / "atlas" / "allods.json", [{"id": "a001", "ru": "Кания", "en": "Kania", "en_official": True,
                                           "climate": "Temperate", "category": "Story allod", "description": ""}])
    write(src / "atlas" / "descriptions.json", [{"part": 2, "section": "1", "ru": "Кания", "en": "Kania", "parent": "",
                                                 "text": "The land of the League."}])
    corpus = tmp_path / "corpus"
    (corpus / "stories").mkdir(parents=True)
    (corpus / "stories" / "memories.txt").write_text("Мне повезло родиться в семье правителей.", encoding="utf-8")
    return root, src, corpus


def build(tmp_path):
    root, src, corpus = make_lore(tmp_path)
    b = lb.Builder(lb.Lore(root), src, corpus)
    b.build()
    out = tmp_path / "out"
    report = b.write(out)
    return out, report


def load(out, rel):
    return json.loads((out / rel).read_text(encoding="utf-8"))


def test_resolve_follows_the_fallback_order():
    texts = {"en": None, "fr": "Bonjour", "ru": "Привет"}
    assert lb.resolve(texts, "en") == ("Bonjour", "fr")
    assert lb.resolve(texts, "fr") == ("Bonjour", "")
    assert lb.resolve({"en": "Hi", "fr": None, "ru": "Привет"}, "fr") == ("Hi", "en")
    assert lb.resolve({"en": None, "fr": None, "ru": "Привет"}, "en") == ("Привет", "ru")


def test_tokens_postings_and_shard_keys():
    assert lb.tokens("Ancient June Magic — the Ёлка!") == ["ancient", "june", "magic", "елка"]
    assert lb.encode_postings([3, 5, 40]) == "3,2,z"
    assert lb.shard_key("кания") == "43a430"
    assert lb.atlas_key("Айрин (Умойр)") == "аирин"


def test_sections_links_and_fallback_texts(tmp_path):
    out, report = build(tmp_path)
    assert report["sections"]["quests"] == 1 and report["sections"]["secrets"] == 1
    quests = load(out, "list/en/quests.json")
    row = quests["rows"][0]
    assert row[0] == "r10" and row[4] == "Wolf Threat" and row[3] & lb.FLAG_EN_MISSING and row[3] & lb.FLAG_REVISED
    body = load(out, f"text/en/quests-{row[2]}.json")["r10"]
    goal = next(t for t in body["t"] if t[0] == "goal")
    assert goal[1] == 0                                   # absent en anglais : la page lit le bloc français
    assert load(out, f"text/fr/quests-{row[2]}.json")["r10"]["t"][0][1] == "Tuez les loups."
    start = next(t for t in body["t"] if t[0] == "startText")
    assert start[1] == "Listen, hero." and start[2] == lb.TEXT_REVISED
    assert body["l"]["secrets"] == [["secrets/r50", "Ancient June Magic"]]
    assert body["l"]["characters"] == [["characters/r20", "Catherina"]]
    assert body["l"]["region"] == [["atlas/z-Kania", "Kania"]]
    # le PNJ porte sa réplique et ses quêtes ; la région renvoie vers quêtes et PNJ
    npc = load(out, "text/en/characters-0.json")["r20"]
    assert npc["i"][0]["h"][1] == "Who are you?" and npc["l"]["quests"] == [["quests/r10", "Wolf Threat"]]
    atlas = load(out, "list/en/atlas.json")
    region = next(r for r in atlas["rows"] if r[0] == "z-Kania")
    region_body = load(out, f"text/en/atlas-{region[2]}.json")["z-Kania"]
    assert region_body["l"]["quests"][0][0] == "quests/r10" and region_body["l"]["characters"][0][0] == "characters/r20"
    secret = load(out, "text/en/secrets-0.json")["r50"]
    assert secret["i"][0]["n"] == 1 and secret["i"][0]["l"]["quests"] == [["quests/r10", "Wolf Threat"]]


def test_community_entries_are_credited_and_keep_the_russian_original(tmp_path):
    out, _ = build(tmp_path)
    lib = load(out, "list/en/library.json")
    row = next(r for r in lib["rows"] if r[0] == "c-memories")
    assert row[3] & lb.FLAG_COMMUNITY and row[4] == "Memories of Catherina"
    body = load(out, f"text/en/library-{row[2]}.json")["c-memories"]
    assert body["m"]["credit"] == "Atlas: M. T." and body["m"]["translated"] == lb.TRANSLATED_BY
    assert body["t"][0][3] == {"md": True} and "family of rulers" in body["t"][0][1]
    assert load(out, f"text/ru/library-{row[2]}.json")["c-memories"]["t"][0][1].startswith("Мне повезло")
    assert load(out, "list/ru/library.json")["rows"][0][4] == "Воспоминания Смеяны"
    allod = load(out, "text/en/atlas-0.json")["a-a001"]
    assert ["climate", "Temperate"] in allod["f"] and allod["t"][0][1] == "The land of the League."
    assert load(out, "meta.json")["credit"]["line"] == "Atlas: M. T."


def test_search_index_directory_and_names(tmp_path):
    out, report = build(tmp_path)
    meta = load(out, "meta.json")
    shard = load(out, f"search/en/{lb.shard_key('wolf')}.json")
    all_ids, title_ids = shard["wolf"].split("|")
    gid = int(all_ids, 36)
    block = load(out, f"dir/en/{gid // meta['dir_block']}.json")
    assert block[gid % meta["dir_block"]][:3] == ["quests", "r10", "Wolf Threat"] and title_ids == all_ids
    ru_shard = load(out, f"search/ru/{lb.shard_key('смеяна')}.json")
    assert "смеяна" in ru_shard
    names = load(out, "names/en.json")
    assert names["Catherina"] == "characters/r20" and names["Kania"].startswith("atlas/")
    # à score égal, les entités nommées (PNJ) passent avant les quêtes
    dir0 = load(out, "dir/en/0.json")
    assert [r[0] for r in dir0].index("characters") < [r[0] for r in dir0].index("quests")


def test_lore_links_walk_up_references_to_a_single_npc():
    # 30 (réplique) ← 31 (interaction) ← 20 (PNJ) ; la quête 10 référence le PNJ 20
    edges = np.array([[31, 30], [20, 31], [10, 20], [10, 99]], dtype=np.int64)
    links = lore.lore_links(edges, {30: "dialogues", 20: "characters", 10: "quests"})
    assert links["dialogue_character"] == {"r30": "r20"}
    assert links["quest_characters"] == {"r10": ["r20"]}
    assert lore.lore_links(np.zeros((0, 2), np.int64), {}) == {"dialogue_character": {}, "dialogue_quest": {}, "quest_characters": {}}


def test_unattached_dialogues_leave_the_characters_list(tmp_path):
    out, report = build(tmp_path)
    assert report["sections"]["dialogues"] == 1 and report["sections"]["characters"] == 1
    assert [r[0] for r in load(out, "list/en/characters.json")["rows"]] == ["r20"]
    assert not (out / "list" / "en" / "dialogues.json").exists()
    index = load(out, "list/dialogues-index.json")
    assert index == {"first": [31]} and load(out, "meta.json")["sections"]["dialogues"]["hidden"] is True
    body = load(out, "text/en/dialogues-0.json")["r31"]
    assert body["n"] == "The wolves are coming back." and body["l"]["quests"] == [["quests/r10", "Wolf Threat"]]
    # toujours trouvable par la recherche
    shard = load(out, f"search/en/{lb.shard_key('coming')}.json")
    ids, acc = [], 0
    for part in shard["coming"].split("|")[0].split(","):
        acc += int(part, 36)
        ids.append(acc)
    rows = [load(out, f"dir/en/{g // 64}.json")[g % 64][:2] for g in ids]
    assert ["dialogues", "r31"] in rows


def test_images_join_the_atlas_and_the_gallery(tmp_path):
    root, src, corpus = make_lore(tmp_path)
    # dossier au nom de l'allod, fichier à son nom ailleurs, illustration d'une rubrique de l'atlas
    write(root / "media.json", {"images": {"aa": [800, 600], "bb": [640, 480], "cc": [1600, 900], "dd": [300, 300]},
                                "files": [["Мир/Кания/1.png", "aa"], ["Разное/Кания 2 old.jpg", "bb"],
                                          ["Разное/logo.png", "dd"]],
                                "docs": [{"doc": "ATLAS ALLODS.docx", "images": [["cc", "2", "1", "Кания"],
                                                                                   ["dd", "", "", ""]]}]})
    write(src / "media-albums.json", {"albums": {"Разное": "Miscellaneous"},
                                      "groups": {"Мир": {"en": "World", "fr": "Monde", "ru": "Мир"}}})
    b = lb.Builder(lb.Lore(root), src, corpus)
    b.build()
    out = tmp_path / "out"
    report = b.write(out)
    assert report["sections"]["gallery"] == 3          # Мир/Кания, Разное, document (Мир n'a pas d'image)
    allod = load(out, "text/en/atlas-0.json")["a-a001"]
    desc = next(t for t in allod["t"] if t[0] == "atlasDescription")
    assert desc[3]["img"] == [["cc", 1600, 900]]        # dans le texte de sa rubrique
    assert allod["p"] == [["aa", 800, 600], ["bb", 640, 480]]
    assert [x[0] for x in allod["l"]["albums"]] == ["gallery/g-mir-kaniya"]
    gallery = load(out, "list/en/gallery.json")
    rows = {r[0]: r for r in gallery["rows"]}
    assert rows["g-mir-kaniya"][4] == "Kania" and rows["g-raznoe"][4] == "Miscellaneous"
    assert rows["g-mir-kaniya"][3] & lb.FLAG_COMMUNITY and gallery["groups"][rows["g-mir-kaniya"][1]]["label"] == "World"
    album = load(out, f"text/en/gallery-{rows['g-mir-kaniya'][2]}.json")["g-mir-kaniya"]
    assert album["p"] == [["aa", 800, 600]] and album["l"]["atlas"] == [["atlas/a-a001", "Kania"]]
    assert album["m"]["credit"] == "Atlas: M. T." and "album" not in album["l"]
    doc = load(out, f"text/en/gallery-{rows['g-doc-atlas-allods'][2]}.json")["g-doc-atlas-allods"]
    assert [it["p"] for it in doc["i"]] == [[["cc", 1600, 900]], [["dd", 300, 300]]]
    assert doc["i"][0]["h"][1] == "Kania" and doc["i"][0]["l"]["atlas"][0][0] == "atlas/a-a001"


def test_image_stem_key_drops_numbers_and_old_suffixes():
    assert lb.image_stem_key("Чумной Город 2.jpg") == lb.atlas_key("Чумной Город")
    assert lb.image_stem_key("Гробница ОЛД.png") == lb.atlas_key("Гробница")
    assert lb.image_stem_key("Остров (3).png") == lb.atlas_key("Остров")
    assert lb.translit_slug("Mdrn world/Даян") == "mdrn-world-dayan"


def test_perceptual_copies_are_shown_once_per_entry(tmp_path):
    root, src, corpus = make_lore(tmp_path)
    write(root / "media.json", {"images": {"aa": [800, 600], "bb": [640, 480], "cc": [10, 10]},
                                "hash": {"aa": "ffff0000ffff0000", "bb": "ffff0000ffff0001", "cc": "0123456789abcdef"}})
    b = lb.Builder(lb.Lore(root), src, corpus)
    assert [x[0] for x in b.imgs(["aa", "bb", "cc"])] == ["aa", "bb", "cc"]
    assert [x[0] for x in b.imgs(["aa", "bb", "cc"], perceptual=True)] == ["aa", "cc"]
    assert [x[0] for x in b.imgs(["bb", "cc"], ["aa"], perceptual=True)] == ["cc"]
