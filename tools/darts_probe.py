# One-off: saves raw darts sources to probe/ so their formats can be inspected.
import json, os, urllib.request, urllib.parse
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "PitchOracle/1.0 (github.com/markbrown3000/pitch-oracle)"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read().decode("utf-8", "replace")
    except Exception as e: return "ERROR " + repr(e)
def save(name, txt): open("probe/" + name, "w").write(txt[:3_000_000])
W = "https://en.wikipedia.org/w/api.php?"
save("wiki_search.json", get(W + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": "2026 darts PDC", "srlimit": 100, "format": "json"})))
save("wiki_search2.json", get(W + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": "intitle:2026 darts", "srlimit": 100, "format": "json"})))
for t in ["2026 Grand Slam of Darts", "2026 PDC Pro Tour", "2026 World Grand Prix (darts)", "2026 European Championship (darts)", "2027 PDC World Darts Championship", "2026 PDC Players Championship Finals", "2026 World Series of Darts Finals", "2026 Premier League Darts", "PDC Order of Merit"]:
    save("wiki_" + t.replace(" ", "_").replace("(", "").replace(")", "") + ".json", get(W + urllib.parse.urlencode({"action": "parse", "page": t, "prop": "wikitext", "format": "json", "redirects": 1})))
save("poly_tag.json", get("https://gamma-api.polymarket.com/events?" + urllib.parse.urlencode({"tag_slug": "darts", "closed": "false", "limit": 100})))
save("poly_search.json", get("https://gamma-api.polymarket.com/public-search?" + urllib.parse.urlencode({"q": "darts"})))
save("kalshi_series.json", get("https://api.elections.kalshi.com/trade-api/v2/series?category=Sports"))
save("dartsdb_pro.html", get("https://www.dartsdatabase.co.uk/events-pdc-pro.php"))
save("dartsdb_home.html", get("https://www.dartsdatabase.co.uk/"))
print(sorted((f, os.path.getsize("probe/" + f)) for f in os.listdir("probe")))
