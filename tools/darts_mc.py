# Players Championship results (every round) from Mastercaller, kept in data/darts_pc.json so each event is read once.
import re, json, time, datetime, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (compatible; PitchOracle/1.0; +https://github.com/markbrown3000/pitch-oracle)"}
BASE = "https://mastercaller.com/tournaments/players-championships"
MON = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
TOK = re.compile(r'(?P<date>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2}(?: \d{4})? - \d\d:\d\d)|truncate">(?P<name>[^<]+)</span>|<div class="text-base">\s*(?P<avg>[\d.]+)\s*</div>|rounded-md[^"]*">\s*(?P<score>\d+)\s*</div>|>\s*(?P<round>(?:Last \d+|Round \d+|Quarter-finals|Semi-finals|Final))\s*<')

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: return r.read().decode("utf-8", "replace")
    except Exception as e:
        print("mastercaller", url, e); return None

def parse(html, year, event):
    toks = [(k, m.group(k).strip()) for m in TOK.finditer(html) for k in m.groupdict() if m.group(k)]
    out = []; rnd = ""; i = 0
    while i < len(toks):
        k, v = toks[i]
        if k == "round": rnd = v; i += 1; continue
        if k != "date": i += 1; continue
        # date, nameA, [avgA], [scoreA, scoreB], nameB, [avgB]
        j = i + 1; blk = []
        while j < len(toks) and toks[j][0] not in ("date", "round"): blk.append(toks[j]); j += 1
        names = [x for t, x in blk if t == "name"]; avgs = [float(x) for t, x in blk if t == "avg"]; sc = [int(x) for t, x in blk if t == "score"]
        dm = re.match(r"\w+ (\d{1,2}) (\w{3})", v)
        if len(names) == 2 and len(sc) == 2 and dm and sc[0] != sc[1]:
            d = datetime.date(year, MON[dm.group(2)], int(dm.group(1)))
            out.append({"event": event, "round": rnd, "section": "", "a": names[0], "b": names[1], "sa": sc[0], "sb": sc[1],
                        "bo": 2 * max(sc) - 1, "unit": "legs", "date": d.isoformat(),
                        "avga": avgs[0] if len(avgs) == 2 else None, "avgb": avgs[1] if len(avgs) == 2 else None})
        i = j
    return out

def update(cache_path, today, max_fetch=12):
    try: cache = json.load(open(cache_path))
    except Exception: cache = {"events": {}}
    E = cache.setdefault("events", {})
    idx = get(BASE)
    slugs = sorted(set(re.findall(r'/tournaments/players-championships/((20\d\d)-pc-\d+[^"/]*)"', idx or "")))
    want = [s for s, y in slugs if today.year - 1 <= int(y) <= today.year]
    fetched = 0
    for slug in want:
        e = E.get(slug)
        if e and e.get("matches"): continue                      # finished events never change
        if e and e.get("checked", "") >= (today - datetime.timedelta(days=1)).isoformat(): continue   # not played yet; look again tomorrow
        if fetched >= max_fetch: break
        y = int(slug[:4]); name = f"{y} Players Championship {int(re.match(r'\d+-pc-(\d+)', slug).group(1))}"
        html = get(f"{BASE}/{slug}/results"); fetched += 1; time.sleep(3)
        if html is None: continue
        ms = [m for m in parse(html, y, name) if m["date"] <= today.isoformat()]
        E[slug] = {"name": name, "checked": today.isoformat(), "matches": ms if len(ms) >= 60 else []}   # only keep complete events
    json.dump(cache, open(cache_path, "w"), ensure_ascii=False, separators=(",", ":"))
    allm = [m for e in E.values() for m in e.get("matches", [])]
    print(f"mastercaller: {fetched} pages read, {sum(1 for e in E.values() if e.get('matches'))} events, {len(allm)} matches")
    return allm
