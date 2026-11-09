# One-off: saves Mastercaller pages to probe/ so their format can be inspected.
import os, urllib.request, time
os.makedirs("probe", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; PitchOracle/1.0; +https://github.com/markbrown3000/pitch-oracle)"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r: return r.read().decode("utf-8", "replace")
    except Exception as e: return "ERROR " + repr(e)
for name, url in [("robots.txt", "https://mastercaller.com/robots.txt"),
                  ("pc01.html", "https://mastercaller.com/tournaments/players-championships/2026-pc-01-hildesheim/results"),
                  ("pcs.html", "https://mastercaller.com/tournaments/players-championships"),
                  ("tournaments.html", "https://mastercaller.com/tournaments"),
                  ("pc01-main.html", "https://mastercaller.com/tournaments/players-championships/2026-pc-01-hildesheim")]:
    open("probe/" + name, "w").write(get(url)); time.sleep(2)
print(os.listdir("probe"))
