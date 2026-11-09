# Builds data/us.json for the US sports tab (NHL, NBA, NFL).
# Games, scores and DraftKings odds come from ESPN's public scoreboards; Kalshi's game markets add a second price.
# Each team gets a rating from this season's results (newer games count more); the pick blends that with the market.
import json, math, os, re, sys, time, datetime, urllib.request
import numpy as np

UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle; US sports tab)"}
LEAGUES = {
    "nhl": {"name": "NHL", "sport": "hockey", "start": "2026-10-06", "kalshi": "KXNHLGAME", "ahead": 3},
    "nba": {"name": "NBA", "sport": "basketball", "start": "2026-10-20", "kalshi": "KXNBAGAME", "ahead": 3},
    "nfl": {"name": "NFL", "sport": "football", "start": "2026-09-09", "kalshi": "KXNFLGAME", "ahead": 7},
}
HALF_LIFE = 60; PRIOR_SD = 0.6
STATE = "data/us_state.json"; OUT = "data/us.json"

def get(url, tries=3):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", url[:110], e); time.sleep(3 * (t + 1))
    return None

def dec(a):
    try:
        a = float(str(a).replace("+", ""))
    except Exception: return None
    if a == 0: return None
    return round(1 + a / 100, 3) if a > 0 else round(1 + 100 / -a, 3)

def parse_day(d):
    out = []
    for e in (d or {}).get("events", []):
        try:
            c = e["competitions"][0]; st = e["status"]["type"]
            side = {t["homeAway"]: t for t in c["competitors"]}
            h, a = side["home"], side["away"]
            g = {"id": e["id"], "start": e["date"], "home": h["team"]["abbreviation"], "away": a["team"]["abbreviation"],
                 "homeName": h["team"]["displayName"], "awayName": a["team"]["displayName"], "state": st.get("state"), "done": bool(st.get("completed")),
                 "neutral": bool(c.get("neutralSite"))}
            if g["done"]: g["hs"], g["as"] = int(h.get("score") or 0), int(a.get("score") or 0)
            od = (c.get("odds") or [{}])[0]; ml = od.get("moneyline") or {}
            ho = dec(((ml.get("home") or {}).get("close") or {}).get("odds")) or dec((od.get("homeTeamOdds") or {}).get("moneyLine"))
            ao = dec(((ml.get("away") or {}).get("close") or {}).get("odds")) or dec((od.get("awayTeamOdds") or {}).get("moneyLine"))
            if ho and ao and ho > 1 and ao > 1: g["odds"] = {"h": ho, "a": ao}
            hoo = dec(((ml.get("home") or {}).get("open") or {}).get("odds")); aoo = dec(((ml.get("away") or {}).get("open") or {}).get("odds"))
            if hoo and aoo and hoo > 1 and aoo > 1: g["open"] = {"h": hoo, "a": aoo}
            out.append(g)
        except Exception as ex: print("skip event", ex)
    return out

def games_for(lg, cfg, today):
    path = f"data/us_cache_{lg}.json"
    try: cache = json.load(open(path))
    except Exception: cache = {}
    d0 = datetime.date.fromisoformat(cfg["start"]); d1 = today + datetime.timedelta(days=cfg["ahead"])
    d = d0; fetched = 0
    while d <= d1:
        k = d.isoformat()
        if k in cache and d < today - datetime.timedelta(days=2): d += datetime.timedelta(days=1); continue   # finished days are kept
        js = get(f"https://site.api.espn.com/apis/site/v2/sports/{cfg['sport']}/{lg}/scoreboard?dates={d.strftime('%Y%m%d')}&limit=100"); fetched += 1
        if js is not None: cache[k] = parse_day(js)
        time.sleep(0.4); d += datetime.timedelta(days=1)
    json.dump(cache, open(path, "w"), separators=(",", ":"))
    seen = {}
    for k in sorted(cache):
        for g in cache[k]: seen[g["id"]] = g
    print(lg, "days fetched", fetched, "games", len(seen))
    return sorted(seen.values(), key=lambda g: g["start"])

def kalshi_prices(series):
    """{(away, home): home win chance} from Kalshi's open game markets (tickers end in the team abbreviations)."""
    out = {}
    d = get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}&status=open&with_nested_markets=true&limit=200") or {}
    for ev in d.get("events", []):
        ms = ev.get("markets") or []
        if len(ms) != 2: continue
        m = re.match(r".*-\d{2}[A-Z]{3}\d{2}([A-Z]+)$", ev.get("event_ticker", ""))
        pr = {}
        for mk in ms:
            team = mk["ticker"].rsplit("-", 1)[-1]
            b, a = mk.get("yes_bid_dollars"), mk.get("yes_ask_dollars")
            try:
                b, a = float(b or 0), float(a or 0)
                p = (b + a) / 2 if b > 0 and a > 0 else float(mk.get("last_price_dollars") or 0)
            except Exception: p = 0
            if p > 0: pr[team] = p
        if len(pr) == 2:
            t1, t2 = list(pr); s = pr[t1] + pr[t2]
            out[frozenset((t1, t2))] = {t1: pr[t1] / s, t2: pr[t2] / s}
    return out

def fit(games, asof):
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games}); idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    if not games: return {}, 0.0
    H = np.array([idx[g["home"]] for g in games]); A = np.array([idx[g["away"]] for g in games])
    y = np.array([1.0 if g["hs"] > g["as"] else 0.0 for g in games]); nt = np.array([0.0 if g.get("neutral") else 1.0 for g in games])
    w = np.array([0.5 ** ((asof - datetime.date.fromisoformat(g["start"][:10])).days / HALF_LIFE) for g in games])
    r = np.zeros(n); hfa = 0.15
    for _ in range(60):
        p = 1 / (1 + np.exp(-(r[H] - r[A] + hfa * nt)))
        g_m = w * (y - p); h_m = w * p * (1 - p)
        g = np.zeros(n); np.add.at(g, H, g_m); np.add.at(g, A, -g_m); g -= r / PRIOR_SD ** 2
        h = np.full(n, 1 / PRIOR_SD ** 2); np.add.at(h, H, h_m); np.add.at(h, A, h_m)
        r += g / h
        hfa += (g_m * nt).sum() / max(1e-9, (h_m * nt).sum() + 10)
    return {t: float(r[i]) for t, i in idx.items()}, float(hfa)

def model_p(R, hfa, g):
    return 1 / (1 + math.exp(-(R.get(g["home"], 0) - R.get(g["away"], 0) + (0 if g.get("neutral") else hfa))))

def mkt_p(g, kal=None):
    ps = []
    if g.get("odds"): ih, ia = 1 / g["odds"]["h"], 1 / g["odds"]["a"]; ps.append(ih / (ih + ia))
    if kal is not None: ps.append(kal)
    return sum(ps) / len(ps) if ps else None

def blend(pm, pk, w):
    if pk is None: return pm
    lg = lambda x: math.log(max(1e-6, x) / max(1e-6, 1 - x))
    return 1 / (1 + math.exp(-(w * lg(pk) + (1 - w) * lg(pm))))

def tier(c): return "strong" if c >= 0.70 else "lean" if c >= 0.60 else "toss"

def main():
    now = datetime.datetime.now(datetime.timezone.utc); today = now.date()
    try: state = json.load(open(STATE))
    except Exception: state = {"picks": {}}
    P = state.setdefault("picks", {})
    out = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "leagues": {}}
    for lg, cfg in LEAGUES.items():
        G = games_for(lg, cfg, today)
        done = [g for g in G if g["done"] and g["hs"] != g["as"]]
        # replay: each finished game predicted from earlier games only (refitted daily) and the closing DraftKings price
        rep = []; byday = {}
        for g in done: byday.setdefault(g["start"][:10], []).append(g)
        days = sorted(byday)
        for d in days:
            prev = [g for g in done if g["start"][:10] < d]
            if len(prev) < 20: continue
            R, hfa = fit(prev, datetime.date.fromisoformat(d))
            for g in byday[d]:
                rep.append({"g": g, "pm": model_p(R, hfa, g), "pk": mkt_p(g)})
        # tune the market weight on the replay (log loss), between 0.6 and 1
        best = (None, 0.9)
        for w in (1.0, 0.9, 0.8, 0.7, 0.6):
            xs = [x for x in rep if x["pk"] is not None]
            if len(xs) < 80: break
            ll = sum(-math.log(max(1e-6, blend(x["pm"], x["pk"], w) if x["g"]["hs"] > x["g"]["as"] else 1 - blend(x["pm"], x["pk"], w))) for x in xs) / len(xs)
            if best[0] is None or ll < best[0]: best = (ll, w)
        W = best[1]
        # once 300 live picks with a market price have been settled, tune the weight on those instead (ESPN keeps no past prices)
        lv = [x for k, x in P.items() if k.startswith(lg + ":") and "win" in x and x.get("pk") is not None and x.get("pm") is not None]
        if len(lv) >= 300:
            bw = None
            for w in (1.0, 0.95, 0.9, 0.85, 0.8, 0.7, 0.6):
                ll = sum(-math.log(max(1e-6, blend(x["pm"], x["pk"], w) if x["homeWon"] else 1 - blend(x["pm"], x["pk"], w))) for x in lv) / len(lv)
                if bw is None or ll < bw[0]: bw = (ll, w)
            W = bw[1]
        bets = []
        for x in rep:
            p = blend(x["pm"], x["pk"], W); hw = x["g"]["hs"] > x["g"]["as"]; c = max(p, 1 - p); pick_home = p >= 0.5
            o = x["g"].get("odds", {}).get("h" if pick_home else "a")
            bets.append({"date": x["g"]["start"][:10], "c": round(c, 3), "o": o, "win": pick_home == hw, "t": f'{x["g"]["home"] if pick_home else x["g"]["away"]} v {x["g"]["away"] if pick_home else x["g"]["home"]}'})
        R, hfa = fit(done, today)
        kal = kalshi_prices(cfg["kalshi"])
        upcoming = []
        for g in G:
            if g["done"]: continue
            st = datetime.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
            k = kal.get(frozenset((g["home"], g["away"])))
            pk = mkt_p(g, k[g["home"]] if k else None); pm = model_p(R, hfa, g); p = blend(pm, pk, W)
            key = f"{lg}:{g['id']}"
            if st > now and g["state"] == "pre":
                c = max(p, 1 - p); ph = p >= 0.5
                P[key] = {"lg": lg, "start": g["start"], "home": g["homeName"], "away": g["awayName"], "p": round(p, 4), "pick": g["homeName"] if ph else g["awayName"],
                          "c": round(c, 4), "o": (g.get("odds") or {}).get("h" if ph else "a"), "pm": round(pm, 4), "pk": round(pk, 4) if pk is not None else None}
                if st < now + datetime.timedelta(days=cfg["ahead"]):
                    upcoming.append({"id": g["id"], "start": g["start"], "home": g["homeName"], "away": g["awayName"], "p": round(p, 4), "pm": round(pm, 4),
                                     "dk": g.get("odds"), "kalshi": round(k[g["home"]], 3) if k else None})
        # settle live picks
        for g in done:
            x = P.get(f"{lg}:{g['id']}")
            if x and "win" not in x:
                x["win"] = (x["pick"] == g["homeName"]) == (g["hs"] > g["as"]); x["homeWon"] = g["hs"] > g["as"]; x["score"] = f'{g["hs"]}–{g["as"]}'
        live = [x for k, x in P.items() if k.startswith(lg + ":") and "win" in x]
        summ = lambda xs: {t: {"n": sum(1 for x in xs if tier(x["c"]) == t), "won": sum(1 for x in xs if tier(x["c"]) == t and x["win"])} for t in ("strong", "lean", "toss")}
        ratings = sorted(({"team": next((g["homeName"] for g in G if g["home"] == t), t), "r": round(v, 3)} for t, v in R.items()), key=lambda x: -x["r"])
        out["leagues"][lg] = {"name": cfg["name"], "w": W, "games": len(done), "upcoming": upcoming,
                              "record": {"live": summ(live), "replay": summ([{"c": b["c"], "win": b["win"]} for b in bets])},
                              "recent": sorted(live, key=lambda x: x["start"], reverse=True)[:30],
                              "replay": [b for b in bets if b["c"] >= 0.6], "ratings": ratings}
        print(lg, "market weight", W, "replay", out["leagues"][lg]["record"]["replay"], "upcoming", len(upcoming), "kalshi", len(kal))
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    json.dump(state, open(STATE, "w"), separators=(",", ":"))

if __name__ == "__main__":
    main()
