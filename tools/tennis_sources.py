"""Pull tennis match prices and results from Kalshi and Polymarket for the GitHub copy of Pitch Oracle.
python3 tools/tennis_sources.py feed.json markets.json
 - markets.json: upcoming matches with both players' prices (the format tools/tennis.js reads)
 - feed.json:    finished matches from the last 3 days, as a results feed (winner only, no set scores)
Kalshi lists ATP and WTA tour matches; Polymarket also lists Challengers and WTA 125s.
A Polymarket event at a tournament Kalshi doesn't list is treated as a Challenger / WTA 125.
"""
import json, re, sys, time, unicodedata, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (PitchOracle tennis)"}
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(days=3)

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1: print("WARN fetch failed:", url, e); return None
            time.sleep(3 * (i + 1))

def iso(s):
    if not s: return None
    s = str(s).replace(" ", "T").replace("+00", "+00:00") if "+00" in str(s) and "+00:00" not in str(s) else str(s).replace(" ", "T")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception: return None
def z(d): return d.strftime("%Y-%m-%dT%H:%M:%SZ")
def norm(s):
    s = unicodedata.normalize("NFD", s or ""); s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s)).strip()
def pair_key(a, b): return " | ".join(sorted([" ".join(sorted(norm(a).split())), " ".join(sorted(norm(b).split()))]))
def last_first(full):  # "Jan-Lennard Struff" -> "Struff, Jan-Lennard" (the feed format tennis.js expects)
    t = full.strip().split()
    return full if len(t) < 2 else t[-1] + ", " + " ".join(t[:-1])

markets, finals = [], {}
kalshi_events = set()

# ---------- Kalshi ----------
def kalshi_tournament(rules):
    m = re.search(r"in the \d{4} (ATP|WTA) (.+?) (Round|Quarter|Semi|Final|Qualif|Group)", rules or "")
    return (m.group(1), m.group(2).strip()) if m else (None, None)
def price(m):
    b, a, l = (float(m.get(k) or 0) for k in ("yes_bid_dollars", "yes_ask_dollars", "last_price_dollars"))
    return round(100 * ((a + b) / 2 if a > 0 and b > 0 else l), 1)
for series, tour in (("KXATPMATCH", "atp"), ("KXWTAMATCH", "wta")):
    cursor, pages = "", 0
    while pages < 10:
        d = get(f"https://api.elections.kalshi.com/trade-api/v2/events?series_ticker={series}&status=open&with_nested_markets=true&limit=200" + (f"&cursor={cursor}" if cursor else ""))
        if not d: break
        for ev in d.get("events", []):
            ms = [m for m in ev.get("markets", []) if m.get("yes_sub_title")]
            if len(ms) != 2: continue
            _, tname = kalshi_tournament(ms[0].get("rules_primary"))
            if tname: kalshi_events.add(norm(tname))
            start = iso(ms[0].get("occurrence_datetime"))
            if not start or start <= NOW: continue
            p1, p2 = price(ms[0]), price(ms[1])
            if p1 <= 0 or p2 <= 0: continue
            markets.append({"src": "kalshi", "tour": tour, "tournament": tname or "", "start": z(start), "p1": ms[0]["yes_sub_title"], "p2": ms[1]["yes_sub_title"], "price1": p1, "price2": p2, "status": "upcoming"})
        cursor = d.get("cursor") or ""; pages += 1
        if not cursor: break
    # results: settled markets from the last 3 days
    d = get(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=settled&limit=1000&min_close_ts={int(SINCE.timestamp())}") or {}
    byev = {}
    for m in d.get("markets", []): byev.setdefault(m.get("event_ticker"), []).append(m)
    for et, ms in byev.items():
        if len(ms) != 2: continue
        win = [m for m in ms if m.get("result") == "yes"]
        if len(win) != 1: continue  # void / not played
        _, tname = kalshi_tournament(ms[0].get("rules_primary"))
        if tname: kalshi_events.add(norm(tname))
        start = iso(ms[0].get("occurrence_datetime"))
        if not start: continue
        a, b = ms[0]["yes_sub_title"], ms[1]["yes_sub_title"]
        finals[(pair_key(a, b), start.date().isoformat())] = {"id": "kx:" + et, "tour": tour, "tournament": tname or "", "start": start, "a": a, "b": b, "a_won": win[0] is ms[0]}

# ---------- Polymarket ----------
def lower_tier(tname):
    words = set(norm(tname).split()) - {"open", "tennis", "the", "masters", "international", "championships", "cup", "de", "rolex", "prudential"}
    return not any(words & set(k.split()) for k in kalshi_events)
for series, tour in (("atp", "atp"), ("wta", "wta")):
    for closed in ("false", "true"):
        q = {"series_slug": series, "closed": closed, "limit": 300, "order": "startDate", "ascending": "false"}
        d = get("https://gamma-api.polymarket.com/events?" + urllib.parse.urlencode(q)) or []
        for ev in d:
            title = ev.get("title") or ""
            if ":" not in title or " vs " not in title: continue
            tname = title.split(":", 1)[0].strip()
            mk = None
            for m in ev.get("markets", []):
                try: outs = json.loads(m.get("outcomes") or "[]"); prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                except Exception: continue
                if len(outs) == 2 and len(prices) == 2 and "yes" not in [o.lower() for o in outs]: mk = (m, outs, prices); break
            if not mk: continue
            m, outs, prices = mk
            start = iso(m.get("gameStartTime") or ev.get("startTime") or ev.get("endDate"))
            if not start: continue
            t = ("chal" if tour == "atp" else "w125") if lower_tier(tname) else tour
            if closed == "false":
                if start <= NOW or start > NOW + timedelta(days=2) or min(prices) <= 0: continue
                markets.append({"src": "poly", "tour": t, "tournament": tname, "start": z(start), "p1": outs[0], "p2": outs[1], "price1": round(100 * prices[0], 1), "price2": round(100 * prices[1], 1), "status": "upcoming"})
            else:
                if start < SINCE or sorted(prices) != [0.0, 1.0]: continue
                k = (pair_key(outs[0], outs[1]), start.date().isoformat())
                if k in finals: continue  # Kalshi already has it
                finals[k] = {"id": "pm:" + (ev.get("slug") or title), "tour": t, "tournament": tname, "start": start, "a": outs[0], "b": outs[1], "a_won": prices[0] == 1.0}

# ---------- write ----------
LABEL = {"atp": ("ATP", "Men"), "chal": ("ATP Challenger", "Men"), "wta": ("WTA", "Women"), "w125": ("WTA 125", "Women")}
games = []
for f in finals.values():
    pre, sex = LABEL[f["tour"]]
    games.append({"id": f["id"], "status": "final", "start_time": z(f["start"]), "home": "A", "away": "B",
                  "teams": {"A": {"name": last_first(f["a"])}, "B": {"name": last_first(f["b"])}},
                  "tournament": f"{pre} {f['tournament']} {sex} Singles", "score": {"A": 1 if f["a_won"] else 0, "B": 0 if f["a_won"] else 1}, "sets": []})
json.dump({"games": games}, open(sys.argv[1], "w"))
json.dump({"matches": markets}, open(sys.argv[2], "w"))
by = {}
for m in markets: by[m["src"]] = by.get(m["src"], 0) + 1
print(f"sources: {len(markets)} upcoming prices {by}, {len(games)} results from the last 3 days, Kalshi tournaments: {sorted(kalshi_events)}")
