# Boils football-data's two spreadsheets (about 8 MB) down to the rows and columns the page uses, in data/fd_rows.json,
# so phones download a few hundred KB instead. The new-leagues file keeps only the latest two seasons of each country.
import json, re, datetime, openpyxl
KEEP = re.compile(r"^(Div|Date|Time|HomeTeam|AwayTeam|Home|Away|FTHG|FTAG|HG|AG|Country|League|Season|HST|AST|HxG|AxG)$|^(B365|Avg|Max|PS)(C)?(H|D|A|>2\.5|<2\.5)$")
def rows(path, sheet_as_div=False):
    out = []
    wb = openpyxl.load_workbook(path, read_only=True)
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True); h = next(it, None)
        if not h: continue
        cols = [(i, c) for i, c in enumerate(h) if c and KEEP.match(str(c))]
        for r in it:
            d = {}
            for i, c in cols:
                v = r[i] if i < len(r) else None
                if v is None or v == "": continue
                if isinstance(v, (datetime.datetime, datetime.date)): v = v.strftime("%d/%m/%Y")
                elif isinstance(v, datetime.time): v = v.strftime("%H:%M")
                elif isinstance(v, float) and v.is_integer() and c in ("FTHG", "FTAG", "HG", "AG", "HST", "AST", "Season"): v = int(v)
                d[c] = str(v) if c in ("Season", "Date", "Time") else v
            if sheet_as_div and "Div" not in d: d["Div"] = ws.title
            if d: out.append(d)
    return out
main = rows("data/all-euro-data-2026-2027.xlsx")
new = []
try:
    allnew = rows("data/new_leagues_data.xlsx", sheet_as_div=True)
    by = {}
    for r in allnew: by.setdefault(r.get("Div"), set()).add(str(r.get("Season")))
    keep = {k: sorted(v)[-2:] for k, v in by.items()}
    new = [r for r in allnew if str(r.get("Season")) in keep.get(r.get("Div"), [])]
except Exception as e: print("new leagues:", e)
json.dump({"made": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "main": main, "new": new}, open("data/fd_rows.json", "w"), separators=(",", ":"))
print("main rows", len(main), "new-league rows", len(new))
