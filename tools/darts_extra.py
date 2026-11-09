# Extras for the Darts tab:
#  - outrights(): each player's chance of winning a knockout event, by playing out the rest of the draw many times;
#  - mc_upcoming(): order of play (UK times) and any drawn matches from Mastercaller for TV events running now.
import re, random, datetime, urllib.request, time
from darts_parse import key
import darts_model as DM

def outrights(ev_matches, R, stage=True, sims=20000, seed=7):
    """ev_matches: every bracket match parsed from one event page (played or not). Returns None if the draw can't be simulated."""
    br = [m for m in ev_matches if m.get("br") is not None and re.match(r"\d+TeamBracket", m.get("tpl") or "")]   # qualifying mini-brackets are left out
    if not br: return None
    # the first round is RD1 of the biggest bracket template(s); split draws (two halves + a finals bracket) are joined in page order
    size = {}
    for m in br:
        if m["rd"] == 1: size[m["br"]] = size.get(m["br"], 0) + 1
    if not size: return None
    big = max(size.values()); halves = sorted(b for b, n in size.items() if n == big)
    first = sorted([m for m in br if m["br"] in halves and m["rd"] == 1], key=lambda m: (m["br"], m["slot"]))
    n = len(first)
    if n < 4 or n & (n - 1): return None                     # needs a clean 2^k draw with no byes
    big_rounds = max(m["nr"] for m in br if m["br"] in halves)
    # format of each depth: from the big templates, then from the finals template
    fmt = {}
    for m in br:
        d = m["rd"] if m["br"] in halves else big_rounds + m["rd"]
        if m["bo"] and d not in fmt: fmt[d] = (m["bo"], m["unit"])
    depth_total = n.bit_length()   # rounds until one player is left
    played = {}
    for m in ev_matches:
        if m["sa"] is not None and m["sb"] is not None and m["sa"] != m["sb"]:
            played[frozenset((key(m["a"]), key(m["b"])))] = m["a"] if m["sa"] > m["sb"] else m["b"]
    names = {}
    for m in first:
        for s in "ab": names[key(m[s])] = m[s]
    cache = {}
    def p_win(a, b, d):
        k = (a, b, d)
        if k not in cache:
            bo, unit = fmt.get(d, fmt.get(max(fmt) if fmt else 1, (11, "legs")))
            cache[k] = DM.predict(R, names.get(a, a), names.get(b, b), bo, unit, stage=stage)[0]
        return cache[k]
    rng = random.Random(seed)
    reach = {k: [0] * (depth_total + 1) for k in names}
    start = [(key(m["a"]), key(m["b"])) for m in first]
    for _ in range(sims):
        field = [x for pair in start for x in pair]
        for d in range(1, depth_total + 1):
            nxt = []
            for i in range(0, len(field), 2):
                a, b = field[i], field[i + 1]
                w = played.get(frozenset((a, b)))
                if w is not None: w = key(w)
                else: w = a if rng.random() < p_win(a, b, d) else b
                nxt.append(w); reach[w][d] += 1
            field = nxt
    rows = [{"name": names[k], "win": round(100 * c[depth_total] / sims, 1), "final": round(100 * c[depth_total - 1] / sims, 1), "sf": round(100 * c[depth_total - 2] / sims, 1) if depth_total >= 3 else None} for k, c in reach.items()]
    rows.sort(key=lambda r: -r["win"])
    alive = {key(m["a"]) for m in first} | {key(m["b"]) for m in first}
    return {"players": [r for r in rows if r["win"] > 0 or r["final"] > 0][:16], "field": n * 2}

# ---- Mastercaller order of play ----
UA = {"User-Agent": "Mozilla/5.0 (compatible; PitchOracle/1.0; +https://github.com/markbrown3000/pitch-oracle)"}
TV = [("Grand Slam of Darts", "grand-slam-of-darts"), ("Players Championship Finals", "players-championship-finals"), ("PDC World Darts Championship", "pdc-world-championship"),
      ("Premier League Darts", "premier-league"), ("World Matchplay", "world-matchplay"), ("World Grand Prix", "world-grand-prix"), ("UK Open", "uk-open"),
      ("European Championship", "european-championship"), ("World Series of Darts Finals", "world-series-of-darts-finals"), ("Masters", "the-masters")]
MON = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
TOK = re.compile(r'(?P<date>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2}(?: \d{4})? - \d\d:\d\d)|truncate">(?P<name>[^<]+)</span>|rounded-md[^"]*">\s*(?P<score>\d+)\s*</div>|>\s*(?P<round>(?:Group [A-Z]+|Last \d+|Round \d+|Quarter-finals|Semi-finals|Final))\s*<')

def uk_time(d, hm):
    """Mastercaller shows Central European time; the UK is one hour behind all year round."""
    h, m = map(int, hm.split(":"))
    t = datetime.datetime(d.year, d.month, d.day, h, m) - datetime.timedelta(hours=1)
    return t.date().isoformat(), t.strftime("%H:%M")

def mc_upcoming(title, year, start):
    slug = next((s for name, s in TV if name in title), None)
    if not slug: return []
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://mastercaller.com/tournaments/{slug}/{year}/results", headers=UA), timeout=60) as r: html = r.read().decode("utf-8", "replace")
    except Exception as e:
        print("mastercaller", slug, year, e); return []
    toks = [(k, m.group(k).strip()) for m in TOK.finditer(html) for k in m.groupdict() if m.group(k)]
    out = []; rnd = ""; when = None; names = []; scores = []; begun = False
    def flush():
        nonlocal names, scores, when
        if len(names) == 2 and not scores:
            row = {"a": names[0].replace("&#039;", "'"), "b": names[1].replace("&#039;", "'"), "round": rnd}
            if when: row["date"], row["time"] = when
            out.append(row)
        names, scores, when = [], [], None
    for k, v in toks:
        if k == "round": flush(); rnd = v; begun = True
        elif k == "date":
            flush()
            dm = re.match(r"\w+ (\d{1,2}) (\w{3}) - (\d\d:\d\d)", v)
            if dm:
                mo = MON[dm.group(2)]; y = (start.year + (1 if mo < start.month else 0)) if start else year
                try: when = uk_time(datetime.date(y, mo, int(dm.group(1))), dm.group(3))
                except ValueError: when = None
        elif k == "name":
            if not begun: continue          # site menu
            if len(names) == 2: flush()
            names.append(v)
        elif k == "score": scores.append(int(v))
    flush()
    # placeholder times far after the event (e.g. 23:30 on the last day for undrawn matches) are dropped by the caller via the draw itself
    return out
