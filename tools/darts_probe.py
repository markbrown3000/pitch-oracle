# One-off: saves Wikipedia wikitext of darts events to probe/ so the parser can be written against it.
import json, os, urllib.request, urllib.parse
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "PitchOracle/1.0 (github.com/markbrown3000/pitch-oracle)"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read().decode("utf-8", "replace")
W = "https://en.wikipedia.org/w/api.php?"
titles = set()
for q in ["intitle:2026 darts", "intitle:2025 darts", "intitle:2026 PDC", "2026 Players Championship darts", "2026 World Matchplay", "2026 UK Open darts", "2026 PDC World Masters"]:
    d = json.loads(get(W + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": q, "srlimit": 100, "format": "json"})))
    titles |= {x["title"] for x in d["query"]["search"]}
keep = sorted(t for t in titles if any(k in t for k in ("Dart", "dart", "PDC", "Players Championship", "World Matchplay", "UK Open", "Masters")) and ("2026" in t or "2025 Grand Slam" in t or "2025 Players Championship" in t or "2025 PDC" in t))
import time
for k in range(0, len(keep), 20):
    chunk = keep[k:k+20]; time.sleep(2)
    d = json.loads(get(W + urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": "|".join(chunk), "format": "json", "formatversion": 2, "redirects": 1})))
    for pg in d["query"]["pages"]:
        if pg.get("revisions"): open("probe/" + pg["title"].replace(" ", "_").replace("/", "_") + ".txt", "w").write(pg["revisions"][0]["slots"]["main"]["content"])
print(len(keep), keep)
