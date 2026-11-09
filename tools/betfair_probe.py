# One-off: does Betfair's login answer from GitHub's servers, or refuse the location? Uses a made-up login, no real account.
import json, urllib.request, urllib.parse
def post(url, data, headers):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, r.read().decode()[:500]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:500]
    except Exception as e: return None, repr(e)
for host in ["identitysso.betfair.com", "identitysso.betfair.es", "identitysso.betfair.it"]:
    print(host, post(f"https://{host}/api/login", {"username": "pitchoracle_probe_x", "password": "not-a-password"},
                     {"X-Application": "pitchoracle-probe", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}))
try:
    with urllib.request.urlopen("https://ipinfo.io/json", timeout=20) as r: print("runner location", json.loads(r.read()).get("country"))
except Exception as e: print("ipinfo", e)
