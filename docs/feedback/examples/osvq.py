"""Independent ground-truth helper: ask OSV and PyPI/npm directly about name==version pairs given as args.
usage: osvq.py pypi:six==1.15.0 npm:lodash==4.17.15"""
import json
import sys
import urllib.request


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def get(url):
    return json.load(urllib.request.urlopen(url, timeout=30))


for arg in sys.argv[1:]:
    eco, rest = arg.split(":", 1)
    name, ver = rest.split("==")
    osv = post("https://api.osv.dev/v1/query", {"package": {"name": name, "ecosystem": "PyPI" if eco == "pypi" else "npm"}, "version": ver})
    ids = sorted(v["id"] for v in osv.get("vulns", []))
    if eco == "pypi":
        latest = get(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
    else:
        latest = get(f"https://registry.npmjs.org/{name}/latest")["version"]
    print(f"{arg:35} latest={latest:10} advisories={len(ids)} {ids[:3]}")
