# Reads Wikipedia wikitext of PDC events and pulls out every match: players, score, format, date, averages.
# Handles bracket templates ({{32TeamBracket ...}}) and results tables (Player | 6 – 3 | Player).
import re, unicodedata, datetime

MONTHS = {m: i for i, m in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"], 1)}
WORDS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,"twenty-one":21,"twenty-three":23,"twenty-five":25,"thirty-one":31,"thirty-five":35}

def key(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", s).strip()

def clean_name(s):
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]*>|'''?|\{\{nowrap\|", "", s)
    return re.sub(r"\s+", " ", s).strip(" }|")

FLAG = re.compile(r"\{\{(?:#invoke:DartsRankings\|)?(?:PDCFlagR?|flagathlete|flagicon athlete)\|([^{}]*?(?:\[\[[^\]]*\]\][^{}]*?)?)\}\}", re.I)

def parse_flag(inner):
    parts = re.split(r"\|(?![^\[]*\]\])", inner)
    name = clean_name(parts[0]); avg = None
    for p in parts[1:]:
        m = re.match(r"\s*avg\s*=\s*([\d.]+)", p)
        if m:
            try: avg = float(m.group(1))
            except ValueError: pass
    return name, avg

def best_of(text):
    m = re.search(r"best of (\d+|[a-z-]+) (legs|sets)", text or "", re.I)
    if not m: return None, None
    n = m.group(1).lower(); n = int(n) if n.isdigit() else WORDS.get(n)
    return n, m.group(2).lower()

def find_dates(text, year):
    """Every 'd Month [yyyy]' in text, as dates (year guessed when missing)."""
    out = []
    for m in re.finditer(r"(\d{1,2})\s*(?:–\s*\d{1,2}\s*)?(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+(\d{4}))?", text or ""):
        y = int(m.group(3)) if m.group(3) else year
        try: out.append(datetime.date(y, MONTHS[m.group(2).lower()], int(m.group(1))))
        except ValueError: pass
    return out

def event_range(text, title):
    year = int(re.search(r"(20\d\d)", title).group(1))
    m = re.search(r"\|\s*dates\s*=([^\n]*)", text)
    ds = find_dates(m.group(1), year) if m else []
    if ds:
        a, b = min(ds), max(ds)
        # "15 December – 3 January" with only one year written
        if b < a: b = b.replace(year=b.year + 1)
        if (b - a).days > 60 and a.month == 12: pass
        return a, b
    return None, None

def template_blocks(text, pattern):
    """Yield (start, end, body) for each {{...}} template whose head matches pattern, with nested braces."""
    for m in re.finditer(pattern, text):
        i = m.start(); depth = 0; j = i
        while j < len(text) - 1:
            if text[j:j+2] == "{{": depth += 1; j += 2; continue
            if text[j:j+2] == "}}":
                depth -= 1; j += 2
                if depth == 0: break
                continue
            j += 1
        yield i, j, text[i:j]

def params(body):
    out = {}; cur = None
    for line in body.split("\n"):
        m = re.match(r"\s*\|\s*([A-Za-z0-9_-]+)\s*=(.*)$", line)
        if m: cur = m.group(1); out[cur] = m.group(2).strip()
        elif cur and not line.strip().startswith("|") and not line.strip().startswith("}}"): out[cur] += " " + line.strip()
    return out

def score_int(s):
    s = re.sub(r"<[^>]*>|'''?|\{\{[^}]*\}\}|\(.*?\)", "", s or "").strip()
    m = re.match(r"^(\d+)", s)
    return int(m.group(1)) if m else None

def parse_page(title, text):
    """-> list of dicts: event, round, a, b, sa, sb (None if not played), bo, unit, date, avga, avgb, section"""
    a0, b0 = event_range(text, title)
    year = int(re.search(r"(20\d\d)", title).group(1))
    default_bo, default_unit = best_of(re.sub(r"\{\{.*?\}\}", "", text[:20000]))
    matches = []
    heads = [(m.start(), m.group(2).strip()) for m in re.finditer(r"^(={2,4})\s*([^=]+?)\s*\1\s*$", text, re.M)]
    def section_at(pos):
        h = [t for p, t in heads if p < pos]
        return h[-1] if h else ""
    def section_text(pos):
        st = max([p for p, t in heads if p < pos] or [0])
        nx = min([p for p, t in heads if p > st] or [len(text)])
        return text[st:nx]
    spans = []
    for bi, (s, e, body) in enumerate(template_blocks(text, r"\{\{(?:#invoke:bracket\|)?\s*\d+TeamBracket")):
        spans.append((s, e))
        P = params(body)
        sec = section_at(s); stxt = section_text(s)
        sdates = find_dates(re.sub(r"<ref.*?(?:</ref>|/>)", "", stxt.split("{{")[0], flags=re.S), year)
        rounds = sorted({int(m.group(1)) for k in P for m in [re.match(r"RD(\d+)-team", k)] if m})
        nr = len(rounds)
        for r in rounds:
            head = P.get(f"RD{r}", "")
            bo, unit = best_of(head)
            if not bo: bo, unit = best_of(stxt.split("{{")[0])
            if not bo: bo, unit = default_bo, default_unit
            hd = find_dates(head, year)
            if hd: d = hd[0]
            elif sdates: d = sdates[0]
            elif a0 and b0: d = a0 + (b0 - a0) * (r - 1) // max(1, nr - 1) if nr > 1 else a0
            else: d = None
            slots = sorted({int(m.group(1)) for k in P for m in [re.match(rf"RD{r}-team0*(\d+)$", k)] if m})
            for k in slots:
                if k % 2 == 0: continue
                ta, tb = P.get(f"RD{r}-team{k:02d}", P.get(f"RD{r}-team{k}")), P.get(f"RD{r}-team{k+1:02d}", P.get(f"RD{r}-team{k+1}"))
                if not ta or not tb: continue
                fa, fb = FLAG.search(ta), FLAG.search(tb)
                if not fa or not fb: continue
                (na, aa), (nb, ab) = parse_flag(fa.group(1)), parse_flag(fb.group(1))
                if not na or not nb or na.lower() in ("bye", "tbd") or nb.lower() in ("bye", "tbd"): continue
                sa = score_int(P.get(f"RD{r}-score{k:02d}", P.get(f"RD{r}-score{k}")))
                sb = score_int(P.get(f"RD{r}-score{k+1:02d}", P.get(f"RD{r}-score{k+1}")))
                matches.append(dict(event=title, round=re.sub(r"<[^>]*>|'''?|\(.*?\)|\{\{nowrap\|1=|\}\}", "", head).split("best of")[0].strip(" ()") or f"Round {r}",
                                    section=sec, a=na, b=nb, sa=sa, sb=sb, bo=bo, unit=unit, date=d.isoformat() if d else None, avga=aa, avgb=ab, br=bi, rd=r, nr=nr, slot=k))
    # results tables outside brackets: flag | score | flag
    rest = list(text);
    for s, e in spans: rest[s:e] = [" "] * (e - s)
    rest = "".join(rest)
    toks = []
    cur_date = None
    for ln in rest.split("\n"):
        st = ln.strip()
        dl = re.fullmatch(r"'*(?:[A-Z][a-z]+day,?\s*)?(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?)'*:?", st)
        if dl:
            ds = find_dates(dl.group(1), year)
            if ds:
                cur_date = ds[0]
                if a0 and cur_date < a0 and cur_date.month < a0.month: cur_date = cur_date.replace(year=cur_date.year + 1)
            continue
        if not (st.startswith("|") or st.startswith("!")):
            if re.match(r"^=", st): toks.append(("H", None, None))
            continue
        for cell in re.split(r"\|\|", st):
            fl = list(FLAG.finditer(cell))
            if fl:
                for f in fl: toks.append(("F", parse_flag(f.group(1)), cur_date))
                continue
            ds = re.search(r"\{\{dart score\|\s*(\d*)\s*\|\s*(\d*)\s*", cell, re.I)
            if ds:
                toks.append(("S", (int(ds.group(1)) if ds.group(1) else None, int(ds.group(2)) if ds.group(2) else None), cur_date)); continue
            c2 = re.sub(r"'''?|<[^>]*>|align=\w+\||style=\"[^\"]*\"\s*\|", "", cell)
            m = re.fullmatch(r"\s*\|?\s*(\d{1,2})\s*[–—-]\s*(\d{1,2})\s*", c2)
            if m: toks.append(("S", (int(m.group(1)), int(m.group(2))), cur_date)); continue
            if re.fullmatch(r"\s*\|?\s*v(s\.?)?\s*", c2, re.I): toks.append(("S", (None, None), cur_date)); continue
            if c2.strip(" |"): toks.append(("X", None, None))
    for i in range(len(toks) - 2):
        if toks[i][0] == "F" and toks[i+1][0] == "S" and toks[i+2][0] == "F":
            (na, aa), (nb, ab) = toks[i][1], toks[i+2][1]; sa, sb = toks[i+1][1]
            d = toks[i][2] or a0
            matches.append(dict(event=title, round="", section="", a=clean_name(na), b=clean_name(nb), sa=sa, sb=sb, bo=None, unit=None,
                                date=d.isoformat() if d else None, avga=aa, avgb=ab, _pos=i))
    # tables don't carry the format: take it from the nearest "best of N legs" in the page, or infer from the score
    for m in matches:
        if m["bo"] is None:
            if m["sa"] is not None and m["sb"] is not None and max(m["sa"], m["sb"]) > 0:
                m["bo"], m["unit"] = 2 * max(m["sa"], m["sb"]) - 1, default_unit or "legs"
            else:
                m["bo"], m["unit"] = default_bo, default_unit
        m.pop("_pos", None)
    # keep dates inside the event's dates (round headers often omit the year, e.g. "29 December" of a Dec–Jan event)
    if a0 and b0:
        for m in matches:
            if not m["date"]: continue
            d = datetime.date.fromisoformat(m["date"])
            for cand in (d, d.replace(year=d.year - 1), d.replace(year=d.year + 1)):
                if a0 - datetime.timedelta(days=3) <= cand <= b0 + datetime.timedelta(days=3): d = cand; break
            m["date"] = d.isoformat()
    # a finished match must have a winner who reached the target
    out = []
    for m in matches:
        if m["sa"] is not None and m["sb"] is not None and m["bo"]:
            need = m["bo"] // 2 + 1
            if max(m["sa"], m["sb"]) != need and not (m["sa"] == m["sb"] == 0):
                # score doesn't fit the stated format (e.g. a different round's format); infer
                m["bo"] = 2 * max(m["sa"], m["sb"]) - 1
        out.append(m)
    return out
