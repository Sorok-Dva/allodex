"""Travellings de mise en scène des cinématiques moteur (`"travelling"` d'un moment de `"cameras"`).

Quand le client ne garde aucun trajet de caméra (scène jouée dans la vue du joueur), le manifeste
posait un **point de vue fixe**. Choix de l'utilisateur (septembre 2026) : chaque point de vue fixe
devient un **petit travelling**, lent et lisible. C'est de la **mise en scène**, pas une donnée du
client ; elle est fondée sur les données de la scène :

* **sujets** : places des acteurs (leur `SpawnLocation`, posées sur le décor), à hauteur de tête
  (`height` du modèle × échelle × `HEAD`) ; un acteur qui paraît plus tard (`appear`) n'entre dans le
  cadre qu'à son apparition ;
* **cadrage sur le locuteur** : pendant chaque réplique (de son départ à la fin de sa voix), la visée
  va vers la tête du locuteur, tempérée vers le centre du groupe (`lean`) pour garder les autres dans
  le champ ; entre les répliques, vers le centre du groupe. La courbe de visée est lissée par un noyau
  gaussien symétrique (`smooth`, en s) : la caméra anticipe un peu la réplique, sans à-coup ;
* **mouvement** : la caméra part du point de vue du manifeste (celui qu'elle gardait fixe), et décrit
  autour du centre du groupe un **arc** de `arc` degrés (réparti de part et d'autre de ce point de
  vue) en se rapprochant de `dolly` (fraction de la distance), sur toute la durée du moment, avec une
  loi d'accélération douce (`smootherstep` : vitesse nulle au début et à la fin) ;
* **visée d'un lieu** (`focus`, point du décor, et `focus_weight`) : la visée est tirée vers ce
  point (l'épave de la Freya que les héros découvrent) ;
* **placement** (`bearing`, degrés, 0 = est, sens trigonométrique ; `distance`, m ; `height`, m au-dessus
  du centre des têtes) : l'œil de départ est posé par rapport au centre du groupe plutôt qu'au point du
  manifeste (devant les locuteurs, d'après le cap qu'ils regardent) ;
* **sol** : l'œil reste à `CLEARANCE` m au moins au-dessus du décor sous lui (`ground`).

Les clés sont posées tous les `STEP` s ; le lecteur les interpole linéairement.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

STEP = 0.25          # s entre deux clés
HEAD = 0.85          # tête : 85 % de la hauteur du modèle
CLEARANCE = 0.8      # m au-dessus du décor sous l'œil
DEFAULTS = {"arc": 14.0, "dolly": 0.12, "lean": 0.65, "smooth": 0.9, "lead": 0.4}


def smootherstep(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


def head_of(actor: dict) -> np.ndarray:
    p = np.array(actor["path"][0]["p"], float)
    h = float(actor.get("height") or 1.2) * float(actor.get("scale") or 1.0)
    return p + np.array([0.0, 0.0, h * HEAD])


def travelling_keys(t0: float, t1: float, eye: list[float], look: list[float] | None, actors: list[dict],
                    lines: list[dict], params: dict | None = None,
                    ground: Callable[[float, float, float], float | None] | None = None) -> tuple[list[dict], list[dict]]:
    """Clés (caméra, visée) d'un travelling de `t0` à `t1`.

    `actors` : acteurs de la scène (`id`, `path`, `height`, `scale`, `appear`) ; `lines` : répliques
    (`start`, `end`, `speaker`) ; `params` : réglages du manifeste (`subjects`, `arc`, `dolly`, `lean`,
    `smooth`, `lead`) ; `ground(x, y, z)` : hauteur du décor sous un point (ou None)."""
    cfg = {**DEFAULTS, **{k: v for k, v in (params or {}).items() if not k.startswith("_")}}
    wanted = cfg.get("subjects")
    subjects = [a for a in actors if (wanted is None or a["id"] in wanted)]
    heads = {a["id"]: head_of(a) for a in subjects}
    appear = {a["id"]: float(a.get("appear") or 0.0) for a in subjects}
    eye0 = np.array(eye, float)
    if not subjects:
        centre_fixed = np.array(look if look is not None else eye, float)
    span = max(t1 - t0, 1e-3)
    n = max(2, int(math.ceil(span / STEP)) + 1)
    times = np.linspace(t0, t1, n)

    def centre(t: float) -> np.ndarray:
        present = [heads[i] for i in heads if appear[i] <= t + 1e-6]
        if not present:
            return centre_fixed if not subjects else np.mean(list(heads.values()), axis=0)
        return np.mean(present, axis=0)

    # visée brute : locuteur (tempéré vers le groupe) pendant sa réplique, sinon le groupe
    raw = []
    for t in times:
        c = centre(t)
        aim = c
        for line in lines:
            sp = line.get("speaker")
            if sp in heads and appear[sp] <= t + 1e-6 and line["start"] - cfg["lead"] <= t < line["end"]:
                aim = c + cfg["lean"] * (heads[sp] - c)
        raw.append(aim)
    raw = np.array(raw)
    sigma = max(float(cfg["smooth"]), 1e-3) / STEP
    radius = int(3 * sigma)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.concatenate([np.repeat(raw[:1], radius, 0), raw, np.repeat(raw[-1:], radius, 0)])
    target = np.stack([np.convolve(padded[:, k], kernel, mode="valid") for k in range(3)], axis=1)

    if cfg.get("focus") is not None:
        w = float(cfg.get("focus_weight", 0.5))
        target = (1 - w) * target + w * np.array(cfg["focus"], float)

    # mouvement de l'œil : arc autour du centre moyen du groupe, rapprochement doux
    pivot = np.mean([centre(t) for t in times], axis=0)
    if cfg.get("bearing") is not None:
        b = math.radians(float(cfg["bearing"]))
        dist = float(cfg.get("distance", 4.5))
        eye0 = pivot + np.array([dist * math.cos(b), dist * math.sin(b), float(cfg.get("height", 0.3))])
    rel = eye0 - pivot
    d0 = math.hypot(rel[0], rel[1])
    a0 = math.atan2(rel[1], rel[0])
    arc = math.radians(float(cfg["arc"]))
    points = []
    floor = None
    for k, t in enumerate(times):
        u = smootherstep((t - t0) / span)
        a = a0 + arc * (u - 0.5)
        d = d0 * (1.0 - float(cfg["dolly"]) * u)
        z = pivot[2] + rel[2] * (d / d0 if d0 > 1e-6 else 1.0)
        p = np.array([pivot[0] + d * math.cos(a), pivot[1] + d * math.sin(a), z])
        if ground is not None and (floor is None or k % 8 == 0):
            g = ground(float(p[0]), float(p[1]), float(p[2]) + 0.5)
            floor = g if g is not None else floor
        if floor is not None and p[2] < floor + CLEARANCE:
            p[2] = floor + CLEARANCE
        points.append(p)
    fmt = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
    return ([{"t": round(float(t), 3), "p": fmt(p)} for t, p in zip(times, points)],
            [{"t": round(float(t), 3), "p": fmt(p)} for t, p in zip(times, target)])


def splice(track: list[dict], keys: list[dict], t0: float, t1: float) -> list[dict]:
    """Remplace les clés de `track` dans [t0, t1) par `keys` (la clé tenue avant la coupe comprise)."""
    kept = [k for k in track if not (t0 - 1e-6 <= k["t"] < t1 - 1e-6)]
    return sorted(kept + [k for k in keys if k["t"] < t1 - 1e-6] +
                  ([{"t": round(t1 - 1e-3, 3), "p": keys[-1]["p"]}] if keys and keys[-1]["t"] >= t1 - 1e-6 else []),
                  key=lambda k: k["t"])
