"""Runs stocktake --format json on every example dir and prints one digest line per finding plus exit code and seconds.
usage: python digest.py STOCKTAKE_EXE EXDIR   (works on Windows and Linux)"""
import json
import subprocess
import sys
import time
from pathlib import Path

exe, ex = sys.argv[1], Path(sys.argv[2])
for d in sorted(p for p in ex.iterdir() if p.is_dir()):
    if d.name.startswith(("e10", "e11", "e12", "e13", "e14", "p")):
        continue
    t = time.time()
    r = subprocess.run([exe, "--root", str(d), "--format", "json"], capture_output=True, text=True)
    dt = time.time() - t
    print(f"## {d.name} exit={r.returncode} t={dt:.1f}s")
    if r.stdout.strip():
        j = json.loads(r.stdout)
        print("  counts", j["counts"], "unread", j["unread_manifests"], "notes", len(j["notes"]), "offline", j["offline"])
        for f in sorted(j["findings"], key=lambda f: (f["source"], f["name"])):
            print("  ", f["source"], f["name"], f["version"], f["status"], f["latest"], len(f["advisories"]))
    else:
        print("  stderr:", r.stderr.strip().replace(str(d), "<dir>")[:200])
