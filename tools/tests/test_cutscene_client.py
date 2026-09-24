"""Déroulé d'un script visuel de buff du client 17.0 (données synthétiques)."""
from types import SimpleNamespace

from tools.cutscene_client import ClientTimeline, _run


def _db():
    """Base factice : un son nommé, un effet de voile noir (fondus 500 ms), des caméras sans points."""
    strings = {100 + 0xA0: "/Cutscenes/Isa/Isa_Fishers_1_Cutscene"}
    return SimpleNamespace(string=lambda off: strings.get(off), ptr=lambda off: 900 if off == 200 + 0x48 else None,
                           i32=lambda off: 500, elements=lambda off, stride: [], floats=lambda off, n: (0.0,) * n)


def _shot(off: int, bound: float) -> dict:
    return {"type": "VisActionList", "play": "Simultaneously", "elements": [{"type": "CameraTrackAction", "offset": off}],
            "playWhile": {"type": "VisActionDelay", "time": bound}}


def test_client_script_chains_bounded_shots_and_starts_the_voice_after_its_delay():
    # légende des pêcheurs d'Isa : voix à 3 s ; voile jusqu'à 2,5 s puis plans de 5,5 et 8 s en séquence
    root = {"type": "VisActionList", "play": "Simultaneously", "elements": [
        {"type": "VisActionList", "play": "InSequence", "elements": [
            {"type": "VisActionDelay", "time": 3.0}, {"type": "Sound2DAction", "offset": 100, "id": "CutsceneSound"}]},
        {"type": "VisActionList", "play": "InSequence", "elements": [
            {"type": "VisActionList", "play": "Simultaneously", "playWhile": {"type": "VisActionDelay", "time": 2.5},
             "elements": [{"type": "PostEffectVisAction", "offset": 200}]},
            {"type": "VisActionList", "play": "InSequence", "elements": [_shot(1, 5.5), _shot(2, 8.0)]}]},
        {"type": "ProceduralEffectVisAction"}]}
    tl = ClientTimeline()
    tl.end = _run(_db(), root, 0.0, tl, None)
    assert [(s["t"], s["until"]) for s in tl.shots] == [(2.5, 8.0), (8.0, 16.0)]
    assert tl.sounds == [{"t": 3.0, "event": "Cutscenes/Isa/Isa_Fishers_1_Cutscene", "id": "CutsceneSound"}]
    assert tl.veils == [{"t": 0.0, "until": 2.5, "fadeIn": 0.5, "fadeOut": 0.5, "texture": None}]
    assert tl.end == 16.0 and tl.ignored == ["ProceduralEffectVisAction"]
