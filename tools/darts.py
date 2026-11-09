# Builds data/darts.json for the Darts tab.
# Results, draws and averages come from Wikipedia's PDC event pages; the model is tools/darts_model.py.
# Picks are frozen the first time a match appears (data/darts_state.json) so the live record is honest.
import json, os, re, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(__file__))
from darts_parse import parse_page, key
import darts_model as DM
import darts_mc

UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle; darts tab)"}
W = "https://en.wikipedia.org/w/api.php?"
SKIP = ("List of", "Challenge Tour", "Development Tour", "Women", "WDF", "World Cup", "Youth", "in PDC", "Pro Tour", "Tour Card")
# tuned on 2026 results (May–Nov), checked on Jan–Apr: see the stage factor in darts_model.fit
KW = dict(avg_w=0.5, half_life=240, prior_sd=0.6, k_avg=0.07, stage_sd=0.2)
def on_stage(ev): return not ("Players Championship" in ev and "Finals" not in ev)
STATE = "data/darts_state.json"; OUT = "data/darts.json"

def get(url, tries=4):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", url[:120], e); time.sleep(5 * (t + 1))
    return None

def titles(today):
    y = today.year; out = set()
    for q in [f"intitle:{y} darts", f"intitle:{y - 1} darts", f"intitle:{y} PDC", f"intitle:{y + 1} PDC", f"{y} Players Championship darts", f"{y} World Matchplay", f"{y} UK Open darts", f"{y} PDC World Masters", f"{y} Players Championship Finals"]:
        d = get(W + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": q, "srlimit": 100, "format": "json"})) or {}
        out |= {x["title"] for x in d.get("query", {}).get("search", [])}
        time.sleep(1)
    def ok(t):
        if any(s in t for s in SKIP): return False
        if not re.search(r"Dart|dart|PDC|Players Championship|World Matchplay|UK Open|Grand Slam", t): return False
        m = re.match(r"(20\d\d) ", t)
        return bool(m) and y - 1 <= int(m.group(1)) <= y + 1
    return sorted(t for t in out if ok(t))

def fetch(ts):
    pages = {}
    for k in range(0, len(ts), 20):
        d = get(W + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": "|".join(ts[k:k + 20]), "format": "json", "formatversion": 2, "redirects": 1})) or {}
        for pg in d.get("query", {}).get("pages", []):
            if pg.get("revisions"): pages[pg["title"]] = pg["revisions"][0]["slots"]["main"]["content"]
        time.sleep(2)
    return pages

def tier(c): return "strong" if c >= 0.70 else "lean" if c >= 0.60 else "toss"

def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:   # local test: a folder of saved wikitext
        pages = {f[:-4].replace("_", " "): open(os.path.join(src, f)).read() for f in os.listdir(src) if f.endswith(".txt") and not any(s.replace(" ", "_") in f for s in SKIP)}
    else:
        pages = fetch(titles(today))
    print(len(pages), "pages")
    pcs = [] if src else darts_mc.update("data/darts_pc.json", today, max_fetch=80)
    allm = list(pcs)
    for t, txt in pages.items():
        if pcs and "Players Championship series" in t: continue   # Mastercaller has every round of these
        try: allm += parse_page(t, txt)
        except Exception as e: print("parse failed", t, e)
    done = [m for m in allm if m["sa"] is not None and m["sb"] is not None and m["sa"] != m["sb"] and m["date"]]
    seen = set(); D = []
    RANK = ["last 128", "round 1", "first round", "last 64", "round 2", "second round", "last 32", "round 3", "third round", "last 16", "round 4", "quarter", "semi", "final"]
    def rr(m):
        r = (m.get("round") or "").lower()
        return next((i for i, k in enumerate(RANK) if r.startswith(k)), 5)
    for m in sorted(done, key=lambda m: (m["date"], rr(m))):
        k = (m["event"], m["date"], *sorted([key(m["a"]), key(m["b"])]), m["sa"] + m["sb"])
        if k not in seen: seen.add(k); D.append(m)
    up = [m for m in allm if m["sa"] is None and m["sb"] is None and m["date"] and m["date"] >= (today - datetime.timedelta(days=1)).isoformat()]
    print(len(D), "results,", len(up), "upcoming")
    R = DM.fit(D, today, **KW)
    # form: last five results per player
    form = {}
    for m in D:
        for me, opp, w in ((m["a"], m["b"], m["sa"] > m["sb"]), (m["b"], m["a"], m["sb"] > m["sa"])):
            form.setdefault(key(me), []).append("W" if w else "L")
    # live picks: freeze the first prediction for each match
    try: state = json.load(open(STATE))
    except Exception: state = {"picks": {}}
    P = state.setdefault("picks", {})
    def mkey(m): return "|".join([m["event"], *sorted([key(m["a"]), key(m["b"])])]) + "|" + (m.get("round") or m["date"] or "")
    upcoming = []
    for m in sorted(up, key=lambda m: (m["date"], m["event"])):
        p, pl = DM.predict(R, m["a"], m["b"], m["bo"], m["unit"], stage=on_stage(m["event"]))
        k = mkey(m)
        if k not in P:
            P[k] = {"event": m["event"], "round": m["round"], "date": m["date"], "a": m["a"], "b": m["b"], "p": round(p, 4), "pick": m["a"] if p >= 0.5 else m["b"], "bo": m["bo"], "unit": m["unit"], "logged": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
        ra, rb = R.get(key(m["a"]), {}), R.get(key(m["b"]), {})
        upcoming.append({"event": m["event"], "round": re.sub(r"\s*\d{1,2}(\s*[–-]\s*\d{1,2})?\s+(January|February|March|April|May|June|July|August|September|October|November|December).*$", "", m["round"] or m["section"] or "").strip(), "date": m["date"], "a": m["a"], "b": m["b"], "bo": m["bo"], "unit": m["unit"],
                         "p": round(p, 4), "avgA": round(ra["avg"], 1) if ra.get("avg") else None, "avgB": round(rb["avg"], 1) if rb.get("avg") else None,
                         "formA": "".join(form.get(key(m["a"]), [])[-5:]), "formB": "".join(form.get(key(m["b"]), [])[-5:])})
    # settle live picks
    res = {mkey(m): m for m in D}
    for k, x in P.items():
        if "win" in x: continue
        m = res.get(k)
        if m is None:   # bracket rounds can be renamed; fall back to event + players
            cands = [mm for mm in D if mm["event"] == x["event"] and sorted([key(mm["a"]), key(mm["b"])]) == sorted([key(x["a"]), key(x["b"])]) and mm["date"] >= x["date"]]
            m = cands[0] if cands else None
        if m:
            winner = m["a"] if m["sa"] > m["sb"] else m["b"]
            x["win"] = key(winner) == key(x["pick"]); x["score"] = f'{m["sa"]}–{m["sb"]}' if key(m["a"]) == key(x["a"]) else f'{m["sb"]}–{m["sa"]}'
    # replay: each result predicted from a fit on earlier matches only (refitted weekly), last ~6 months
    since = (today - datetime.timedelta(days=183)).isoformat()
    test = [m for m in D if m["date"] >= since]
    replay = []; last = None; RR = None
    for d in sorted({m["date"] for m in test}):
        dd = datetime.date.fromisoformat(d)
        if last is None or (dd - last).days >= 7: RR = DM.fit([m for m in D if m["date"] < d], dd, **KW); last = dd
        for m in (x for x in test if x["date"] == d):
            p, _ = DM.predict(RR, m["a"], m["b"], m["bo"], m["unit"], stage=on_stage(m["event"])); c = max(p, 1 - p)
            replay.append({"date": d, "event": m["event"], "a": m["a"], "b": m["b"], "score": f'{m["sa"]}–{m["sb"]}', "p": round(p, 4), "win": (p >= 0.5) == (m["sa"] > m["sb"]), "tier": tier(c)})
    def summary(items):
        out = {}
        for t in ("strong", "lean", "toss"):
            xs = [x for x in items if x["tier"] == t]; out[t] = {"n": len(xs), "won": sum(1 for x in xs if x["win"])}
        return out
    live = [dict(x, tier=tier(max(x["p"], 1 - x["p"]))) for x in P.values() if "win" in x]
    players = sorted(R.values(), key=lambda v: -v["rs"])
    rank = [{"name": v["name"], "r": round(v["rs"], 3), "rf": round(v["r"], 3), "avg": round(v["avg"], 1) if v["avg"] else None, "n": v["n"], "form": "".join(form.get(key(v["name"]), [])[-5:])} for v in players if v["n"] >= 6][:64]
    recent = [dict(x) for x in sorted(live, key=lambda x: x["date"], reverse=True)[:40]]
    out = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "matches": len(D), "since": D[0]["date"] if D else None,
           "upcoming": upcoming, "players": rank, "record": {"live": summary(live), "replay": summary(replay), "replaySince": since},
           "recent": recent, "replayRecent": sorted(replay, key=lambda x: x["date"], reverse=True)[:40]}
    os.makedirs("data", exist_ok=True)
    json.dump(D, open("data/darts_matches.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(state, open(STATE, "w"), ensure_ascii=False, separators=(",", ":"))
    print("upcoming", len(upcoming), "players", len(rank), "replay", summary(replay), "live", summary(live))

if __name__ == "__main__":
    main()
