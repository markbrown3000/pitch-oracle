# Darts player ratings.
# Each player has a rating r; the chance of winning a leg against an opponent is logistic(r_a - r_b).
# Ratings are fitted to legs (or sets) won in past matches, newer matches counting more, and blended
# with each player's recent three-dart average. Match chances follow from the format (first to N legs/sets).
import math, datetime
import numpy as np
from darts_parse import key

def race(p, n):
    """Chance of reaching n wins first when each point is won with probability p."""
    p = min(max(p, 1e-9), 1 - 1e-9); q = 1 - p
    return sum(math.comb(n - 1 + k, k) * p ** n * q ** k for k in range(n))

def match_prob(p_leg, bo, unit):
    if not bo: bo, unit = 11, "legs"
    n = bo // 2 + 1
    if unit == "sets": return race(race(p_leg, 3), n)   # PDC sets are first to 3 legs
    return race(p_leg, n)

def sig(x): return 1 / (1 + np.exp(-x))

def fit(matches, asof, half_life=150, prior_sd=0.35, avg_w=0.5, k_avg=0.075, iters=300):
    """matches: finished matches dated before asof. Returns {key: {"r":..., "avg":..., "n":...}}"""
    players = {}
    for m in matches:
        for side in "ab": players.setdefault(key(m[side]), m[side])
    idx = {k: i for i, k in enumerate(players)}; n = len(idx)
    A, B, W, L, Wt, SET = [], [], [], [], [], []
    avg_sum = np.zeros(n); avg_wt = np.zeros(n); cnt = np.zeros(n)
    for m in matches:
        age = (asof - datetime.date.fromisoformat(m["date"])).days
        w = 0.5 ** (age / half_life)
        i, j = idx[key(m["a"])], idx[key(m["b"])]
        A.append(i); B.append(j); W.append(m["sa"]); L.append(m["sb"]); Wt.append(w); SET.append(m["unit"] == "sets")
        cnt[i] += 1; cnt[j] += 1
        if m.get("avga"): avg_sum[i] += w * m["avga"]; avg_wt[i] += w
        if m.get("avgb"): avg_sum[j] += w * m["avgb"]; avg_wt[j] += w
    A, B, W, L, Wt, SET = map(np.array, (A, B, W, L, Wt, SET))
    # sets: a set is ~ first to 3 legs, so one set carries about the evidence of 3 legs at a steeper slope; approximate by scaling
    scale = np.where(SET, 1.9, 1.0)
    r = np.zeros(n)
    lr = 0.5
    for _ in range(iters):
        p = sig(scale * (r[A] - r[B]))
        g_m = Wt * scale * (W - (W + L) * p)
        g = np.zeros(n); np.add.at(g, A, g_m); np.add.at(g, B, -g_m)
        g -= r / prior_sd ** 2
        h_m = Wt * scale ** 2 * (W + L) * p * (1 - p)
        h = np.full(n, 1 / prior_sd ** 2); np.add.at(h, A, h_m); np.add.at(h, B, h_m)
        r += lr * g / h
    r -= np.median(r)
    # average-based rating, shrunk to the field average for players with little data
    field = (avg_sum.sum() / avg_wt.sum()) if avg_wt.sum() else 90
    avg = (avg_sum + 3 * field * 0 + 3 * (field - 4)) / (avg_wt + 3)   # 3 matches' worth of a slightly-below-field prior
    ra = k_avg * (avg - field)
    out = {}
    for k, i in idx.items():
        out[k] = {"name": players[k], "r": float((1 - avg_w) * r[i] + avg_w * ra[i]), "rl": float(r[i]), "avg": float(avg[i]) if avg_wt[i] else None, "n": int(cnt[i])}
    return out

UNKNOWN = {"r": -0.25, "avg": None, "n": 0}

def predict(R, a, b, bo, unit):
    ra, rb = R.get(key(a), UNKNOWN)["r"], R.get(key(b), UNKNOWN)["r"]
    p_leg = 1 / (1 + math.exp(-(ra - rb)))
    return match_prob(p_leg, bo, unit), p_leg
