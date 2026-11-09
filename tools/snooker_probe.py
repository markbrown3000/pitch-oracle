# One-off: saves Wikipedia snooker pages to probe/ so the parser can be written against them.
import json, os, re, time, urllib.request, urllib.parse
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "PitchOracle/1.0 (https://github.com/markbrown3000/pitch-oracle; snooker tab)"}
W = "https://en.wikipedia.org/w/api.php?"
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return json.loads(r.read().decode("utf-8"))
def pages(ts):
    out = {}
    for k in range(0, len(ts), 20):
        d = get(W + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": "|".join(ts[k:k+20]), "format": "json", "formatversion": 2, "redirects": 1}))
        for pg in d["query"]["pages"]:
            if pg.get("revisions"): out[pg["title"]] = pg["revisions"][0]["slots"]["main"]["content"]
        time.sleep(2)
    return out
seasons = pages(["2025–26 snooker season", "2026–27 snooker season"])
titles = set()
for t, txt in seasons.items():
    open("probe/" + t.replace(" ", "_") + ".txt", "w").write(txt)
    titles |= set(re.findall(r"\[\[((?:2025|2026|2027) [^\]|#]+)", txt))
titles = sorted(t for t in titles if not any(x in t for x in ("Women", "Seniors", "Amateur", "Under-", "qualifying", "Q School", "World Cup", "snooker season")))
print(len(titles), titles)
for t, txt in pages(titles).items(): open("probe/" + t.replace(" ", "_").replace("/", "_") + ".txt", "w").write(txt)
print(os.listdir("probe"))
