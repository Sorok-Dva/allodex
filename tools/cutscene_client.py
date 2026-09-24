"""Déroulé d'un script visuel de buff du client 17.0 (`BuffVisScripts`), pour les cinématiques moteur.

Les scènes d'après 7.0 (Isa, 14.0…) n'ont plus d'arbre serveur : le client ne dit ni qui parle ni
où sont les PNJ, mais le script visuel du buff de cinématique, lui, est complet. Il enchaîne plans de
caméra, voix off, fondus et effets dans un arbre de `VisAction` (`tools/allods_visdb.read_action`).
Ce module l'aplatit en chronologie, avec les règles de l'interprète des fatalités
(`tools/fatality_script.py`), établies sur les données du client :

* `VisActionList` joue ses éléments en séquence (`play` 0, `InSequence`) ou simultanément
  (`play` 1, `Simultaneously`) ; `playWhile` (un `VisActionDelay`) borne la liste à sa durée
  (`+0x70`, champ relevé sur le 17.0 : dans la légende des pêcheurs d'Isa, chaque plan de caméra est
  une liste simultanée bornée par un délai de 5,5 à 9 s, et les six plans une liste en séquence) ;
* `VisActionDelay` dure `time` ; les autres actions sont instantanées : elles posent un événement ;
* `CameraTrackAction` : un **plan**, de son instant à la borne de sa liste (ou au plan suivant, ou à
  la fin du script). Les durées de ses points sont des **poids** étalés sur la durée du plan, la
  dernière ne compte pas (règle des cinématiques 7.0) ; un plan sans borne prend ses durées en secondes ;
* `Sound2DAction`/`Sound3DAction` : son joué une fois (événement FMOD en `+0xA0`) ; projet de voix
  (`Cutscenes/…`) → voix off ;
* `PostEffectVisAction` → `UserPostEffect` (fondus `+0x28`/`+0x2C` en ms, texture multipliée en
  `+0x60` : le carré noir) : voile noir de l'instant de l'action à la borne de sa liste.

Ce que le script ne dit pas n'est pas inventé : les actions non lues sont nommées (`ignored`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.allods_scenes import BUFF_VIS_SCRIPTS, VIS_SCRIPTS_ACTION, read_camera_track
from tools.allods_visdb import read_action

SOUND_EVENT = 0xA0
SOUND_EVENT_OLD = 0x78          # sons des `ClientData` (voir `allods_scenes.SOUND_NAME`)
POST_EFFECT = 0x48
POST_FADE_IN = 0x28
POST_FADE_OUT = 0x2C
POST_TEXTURE = 0x60
UNBOUNDED = 600.0               # borne prêtée à un plan ou un voile sans fin (fin du script)


@dataclass
class ClientTimeline:
    shots: list[dict] = field(default_factory=list)      # {t, until, points, targets}
    sounds: list[dict] = field(default_factory=list)     # {t, event, id}
    veils: list[dict] = field(default_factory=list)      # {t, until, fadeIn, fadeOut, texture}
    ignored: list[str] = field(default_factory=list)
    end: float = 0.0


def _sound_event(db, off: int) -> str | None:
    for rel in (SOUND_EVENT, SOUND_EVENT_OLD):
        name = db.string(off + rel)
        if name and "/" in name:
            return name.lstrip("/")
    return None


def _run(db, node: dict | None, t0: float, tl: ClientTimeline, limit: float | None) -> float:
    if not node:
        return t0
    kind = node.get("type")

    def clip(t: float) -> float:
        return t if limit is None else min(t, limit)

    if limit is not None and t0 >= limit:
        return t0
    if kind == "VisActionList":
        bound = None
        cond = node.get("playWhile")
        if cond:
            if cond.get("type") == "VisActionDelay":
                bound = float(cond.get("time", 0.0))
            else:
                tl.ignored.append(f"playWhile {cond.get('type')}")
        own = None if bound is None else t0 + bound
        sub = own if limit is None else (limit if own is None else min(own, limit))
        end = t0
        if node.get("play") == "Simultaneously":
            for child in node.get("elements", []):
                end = max(end, _run(db, child, t0, tl, sub))
        else:
            for child in node.get("elements", []):
                end = _run(db, child, end, tl, sub)
                if sub is not None and end >= sub:
                    break
        # Une liste bornée tient jusqu'à sa borne : ses actions instantanées (plan, voile) durent
        # jusque-là (`stopWhileWhenElementsEnded` ne l'arrête pas avant : ses éléments ne finissent
        # pas d'eux-mêmes).
        if own is not None:
            end = max(end, own)
        return clip(end)
    if kind == "VisActionDelay":
        return clip(t0 + float(node.get("time", 0.0)))
    if kind == "CameraTrackAction":
        track = read_camera_track(db, node["offset"])
        tl.shots.append({"t": round(t0, 3), "until": None if limit is None else round(limit, 3),
                         "points": track.points, "targets": track.targets})
        return t0
    if kind in ("Sound2DAction", "Sound3DAction"):
        event = _sound_event(db, node["offset"])
        if event:
            tl.sounds.append({"t": round(t0, 3), "event": event, "id": node.get("id")})
        return t0
    if kind == "PostEffectVisAction":
        effect = db.ptr(node["offset"] + POST_EFFECT)
        if effect is not None:
            tex = db.ptr(effect + POST_TEXTURE)
            tl.veils.append({"t": round(t0, 3), "until": None if limit is None else round(limit, 3),
                             "fadeIn": db.i32(effect + POST_FADE_IN) / 1000.0,
                             "fadeOut": db.i32(effect + POST_FADE_OUT) / 1000.0,
                             "texture": tex})
        return t0
    tl.ignored.append(str(kind))
    return t0


def buff_timeline(db, buff: int) -> ClientTimeline:
    """Chronologie du script visuel du buff `buff` (décalage d'une `BuffResource`)."""
    tl = ClientTimeline()
    scripts = db.ptr(buff + BUFF_VIS_SCRIPTS)
    root = read_action(db, db.ptr(scripts + VIS_SCRIPTS_ACTION)) if scripts is not None else None
    tl.end = _run(db, root, 0.0, tl, None)
    # un plan sans borne tient jusqu'au plan suivant, ou jusqu'à la fin du script
    starts = sorted(s["t"] for s in tl.shots)
    for shot in tl.shots:
        if shot["until"] is None:
            later = [t for t in starts if t > shot["t"]]
            shot["until"] = later[0] if later else None
    return tl

