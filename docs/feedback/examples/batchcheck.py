import json, sys, urllib.request
j = json.load(open("logs/e09.json", encoding="utf-8"))
fs = [f for f in j["findings"] if f["version"] and f["ecosystem"] in ("PyPI", "npm")]
seen = {}
for f in fs:
    seen[(f["ecosystem"], f["name"], f["version"])] = f
keys = list(seen)
vuln_osv = set()
for i in range(0, len(keys), 500):
    chunk = keys[i:i+500]
    body = {"queries": [{"package": {"name": n, "ecosystem": e}, "version": v} for e, n, v in chunk]}
    req = urllib.request.Request("https://api.osv.dev/v1/querybatch", json.dumps(body).encode(), {"Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(req, timeout=60))["results"]
    for k, r in zip(chunk, res):
        if r.get("vulns"):
            vuln_osv.add(k)
vuln_st = {k for k, f in seen.items() if f["status"] == "vulnerable"}
print("distinct pkg@ver", len(keys), "OSV-vulnerable", len(vuln_osv), "StockTake-vulnerable", len(vuln_st))
print("only OSV:", sorted(vuln_osv - vuln_st)); print("only StockTake:", sorted(vuln_st - vuln_osv))
