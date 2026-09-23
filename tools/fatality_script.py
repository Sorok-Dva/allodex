"""Interprète hors-ligne des scripts de fatalité (`offenderDeathScript` du `SlonRoot`).

Le client joue, sur la victime, un arbre de `VisAction` (voir `tools/allods_visdb.read_action`).
Ce module l'aplatit en **chronologie** pour un personnage donné : pas d'animation de la
victime, changements d'échelle et de transparence, objets d'effet posés à ses pieds
(`CreatureIndependentFxAction`) ou accrochés à ses locators (`CreatureEffectsAction`),
secousses de caméra. Règles appliquées (données du client, relevées dans les 26 scripts) :

* `VisActionList` joue ses éléments **simultanément** (`play = Simultaneously`) ou **en
  séquence** (`InSequence`, défaut). Sa durée est celle de son plus long élément, ou la somme ;
* `playWhile` (« après la fin de ce script, toute la liste s'arrête », dit le schéma) : un
  `VisActionDelay` borne la liste à sa durée — c'est ainsi que les fatalités de boutique
  enchaînent « 8 s de telle animation, puis telle autre » ; et comme
  `stopWhileWhenElementsEnded` vaut vrai (défaut, et partout dans ces scripts), la liste
  s'arrête aussi dès que ses éléments sont finis : sa durée est le minimum des deux ; un `PredicateCreatureVisCharacterAction` est une
  **condition** sur le gabarit de la victime (les variantes par race du Lotus, de l'Avatar…) ;
  un `PredicateCreatureFlagAction` (`FatalityVictim`) est vrai pendant toute la fatalité ;
* `VisActionDelay` dure `time` ; une animation `CLAMP` ou `DIE` dure sa longueur divisée par
  sa vitesse (longueur propre au squelette de chaque race) puis tient sa dernière pose ; une
  animation `LOOP` n'a pas de fin propre (elle dure jusqu'à la borne de sa liste) ;
* les autres actions sont instantanées : elles déclenchent un événement et rendent la main.

Ce que le client fait sans que les données le disent n'est pas inventé ici : les écarts sont
nommés dans la sortie (`ignored`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Durée prêtée à une animation en boucle sans borne : jamais atteinte en pratique (toutes les
# boucles des fatalités sont bornées par un délai), elle évite une chronologie infinie.
UNBOUNDED_LOOP = 60.0


@dataclass
class Timeline:
    victim: list[dict] = field(default_factory=list)       # {t, end, anim, speed, mode}
    scale: list[dict] = field(default_factory=list)        # {t, scale}
    alpha: list[dict] = field(default_factory=list)        # {t, value, fadeMult, priority}
    spawns: list[dict] = field(default_factory=list)       # objets posés : {t, vot, lifeTime, offset, rotation, scale}
    attached: list[dict] = field(default_factory=list)     # objets accrochés : {t, vot, locator, scale, fadeIn, fadeOut, offset}
    shakes: list[dict] = field(default_factory=list)       # {t, params}
    channels: list[dict] = field(default_factory=list)     # rayons : {t, until, vot, fadeIn, fadeOut, length, start, end}
    tints: list[dict] = field(default_factory=list)        # {t, color, blend, priority, timeOn}
    ignored: list[str] = field(default_factory=list)
    end: float = 0.0


@dataclass
class Context:
    character: str                                          # nom du gabarit (`KaniaMale`…)
    durations: dict[str, float]                             # animation → durée (s) pour ce personnage
    anim_names: dict[int, str]
    timeline: Timeline = field(default_factory=Timeline)


def _condition(node: dict | None, ctx: Context) -> tuple[bool, float | None]:
    """(la liste joue-t-elle ?, borne de durée) d'après son `playWhile`."""
    if not node:
        return True, None
    kind = node.get("type")
    if kind == "VisActionDelay":
        return True, float(node.get("time", 0.0))
    if kind == "PredicateCreatureVisCharacterAction":
        return ctx.character in (node.get("templates") or []), None
    if kind == "PredicateCreatureFlagAction":
        return True, None
    ctx.timeline.ignored.append(f"playWhile {kind}")
    return True, None


def run(node: dict | None, t0: float, ctx: Context, limit: float | None = None) -> float:
    """Joue `node` à partir de `t0` ; renvoie l'instant où il rend la main (≤ `limit`)."""
    if not node:
        return t0
    tl = ctx.timeline
    kind = node.get("type")

    def clip(t: float) -> float:
        return t if limit is None else min(t, limit)

    if limit is not None and t0 >= limit:
        return t0
    if kind == "VisActionList":
        plays, bound = _condition(node.get("playWhile"), ctx)
        if not plays:
            return t0
        own = None if bound is None else t0 + bound
        sub = own if limit is None else (limit if own is None else min(own, limit))
        if node.get("play") == "Simultaneously":
            end = t0
            for child in node.get("elements", []):
                end = max(end, run(child, t0, ctx, sub))
        else:
            end = t0
            for child in node.get("elements", []):
                end = run(child, end, ctx, sub)
                if sub is not None and end >= sub:
                    break
        if own is not None:
            end = min(own, end) if node.get("stopWhileWhenElementsEnded", True) else own
        return clip(end)
    if kind == "VisActionDelay":
        return clip(t0 + float(node.get("time", 0.0)))
    if kind == "CreatureAnimationAction":
        names = [ctx.anim_names.get(i, f"anim{i}") for i in node.get("animations", [])]
        name = names[0] if names else None
        speed = float(node.get("speed") or 1.0)
        mode = node.get("mode", "CLAMP")
        length = ctx.durations.get(name or "", 0.0) / speed if name else 0.0
        end = t0 + (UNBOUNDED_LOOP if mode == "LOOP" else length)
        end = clip(end)
        tl.victim.append({"t": round(t0, 4), "end": round(end, 4), "anim": name, "speed": speed,
                          "mode": mode, "alternatives": names[1:]})
        if name and name not in ctx.durations:
            tl.ignored.append(f"animation absente pour {ctx.character} : {name}")
        return end
    if kind == "CreatureIndependentFxAction":
        if node.get("visObject") is not None:
            tl.spawns.append({"t": round(t0, 4), "vot": node["visObject"], "lifeTime": node.get("lifeTime", 1.0),
                              "offset": node.get("offset"), "rotation": node.get("rotation"),
                              "scale": node.get("scale", 1.0), "isRelative": node.get("isRelative", True)})
        return t0
    if kind == "CreatureEffectsAction":
        for effect in node.get("effects", []):
            if effect.get("visObject") is not None:
                tl.attached.append({"t": round(t0, 4), "vot": effect["visObject"], "locator": effect.get("locator"),
                                    "scale": effect.get("scale", 1.0), "fadeIn": effect.get("fadeIn", 0.0),
                                    "fadeOut": effect.get("fadeOut", 0.0), "offset": effect.get("offset"),
                                    "until": None if limit is None else round(limit, 4)})
        return t0
    if kind == "CreatureScaleAction":
        tl.scale.append({"t": round(t0, 4), "scale": node.get("scale", 1.0)})
        return t0
    if kind == "CreatureSetTransparencyAction":
        tl.alpha.append({"t": round(t0, 4), "value": node.get("transparency", 1.0),
                         "fadeMult": node.get("fadeMult", 1.0), "priority": node.get("priority", 1)})
        return t0
    if kind == "CreatureChannelDirectAction":
        if node.get("visObject") is not None:
            tl.channels.append({"t": round(t0, 4), "until": None if limit is None else round(limit, 4),
                                "vot": node["visObject"], "fadeIn": node.get("fadeIn", 0.0),
                                "fadeOut": node.get("fadeOut", 0.0), "length": node.get("length", 0.0),
                                "velocity": node.get("velocity", 0.0), "start": node.get("start"), "end": node.get("end")})
        return t0
    if kind == "ShakeAction":
        shake = {"t": round(t0, 4)}
        for key in ("amplitude", "radius", "timeScale", "curve"):
            if node.get(key) is not None:
                shake[key] = node[key]
        tl.shakes.append(shake)
        return t0
    if kind == "CreatureColorAction":
        # Teinte de la créature : couleur ARGB atteinte en `timeOn` s, la plus prioritaire l'emporte.
        tl.tints.append({"t": round(t0, 4), "color": node.get("color", 0xFFFFFFFF), "blend": node.get("blend", "DEFAULT"),
                         "priority": node.get("priority", 0), "timeOn": node.get("timeOn", 0.0)})
        return t0
    if kind == "ProceduralEffectVisAction":
        tl.ignored.append(kind)
        return t0
    tl.ignored.append(str(kind))
    return t0


def flatten(script: dict | None, character: str, durations: dict[str, float],
            anim_names: dict[int, str]) -> Timeline:
    ctx = Context(character, durations, anim_names)
    ctx.timeline.end = run(script, 0.0, ctx)
    return ctx.timeline
