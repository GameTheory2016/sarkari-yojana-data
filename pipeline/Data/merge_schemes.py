#!/usr/bin/env python3
"""Merge the per-batch scheme files into Resources/data/schemes_en.json and validate.

Run from the project root:  python3 Data/merge_schemes.py
"""
import json, os, sys, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "Resources", "data")
# The hand-written batches live outside Resources so they are not bundled
# into the app; only the merged schemes_*.json files ship.
WORK = os.path.join(ROOT, "Data", "work")
OUT  = os.path.join(DATA, "schemes_en.json")

CATEGORIES = {"Agriculture","Health","Education","Women","Housing","Employment",
              "Pension","Identity","Utilities","Business","Other"}
REQUIRED = ["id","title","department","level","category","mode","brief","benefit"]

def fail(msg): print("  ERROR:", msg); return 1

def main():
    parts = sorted(glob.glob(os.path.join(WORK, "_part_*.json")))
    if not parts:
        print("No _part_*.json files found in", WORK); return 1

    schemes, seen, errors = [], {}, 0
    for p in parts:
        name = os.path.basename(p)
        try:
            raw = json.load(open(p))
        except Exception as e:
            print(f"{name}: not valid JSON -> {e}"); errors += 1; continue
        recs = raw.get("schemes") if isinstance(raw, dict) else raw
        if not isinstance(recs, list):
            print(f"{name}: no scheme array"); errors += 1; continue
        print(f"{name}: {len(recs)} records")
        for r in recs:
            rid = r.get("id","")
            if not rid:
                errors += fail(f"{name}: record with no id"); continue
            if rid in seen:
                errors += fail(f"{name}: duplicate id '{rid}' (also in {seen[rid]})"); continue
            seen[rid] = name

            for k in REQUIRED:
                if not r.get(k):
                    errors += fail(f"{rid}: missing '{k}'")
            if r.get("level") not in ("Central","State"):
                errors += fail(f"{rid}: level must be Central or State")
            if r.get("level") == "State" and not r.get("state"):
                errors += fail(f"{rid}: State record needs a state name")
            if r.get("level") == "Central" and r.get("state"):
                errors += fail(f"{rid}: Central record must have empty state")
            if r.get("category") not in CATEGORIES:
                errors += fail(f"{rid}: category '{r.get('category')}' not allowed")
            if r.get("mode") not in ("online","offline"):
                errors += fail(f"{rid}: mode must be online or offline")

            if r.get("mode") == "online" and not r.get("applyUrl"):
                errors += fail(f"{rid}: online record needs applyUrl")
            # An offline scheme must say where to hand the form in. A
            # downloadable form is a bonus: plenty of state schemes still issue
            # theirs only at the counter, and the detail screen already hides
            # the download button when formUrl is empty. Requiring one here
            # only tempted writers to invent a URL.
            if r.get("mode") == "offline" and not r.get("submitAt"):
                errors += fail(f"{rid}: offline record needs submitAt")

            for url_key in ("applyUrl","formUrl","portalUrl"):
                u = r.get(url_key,"")
                if u and not re.match(r"^https?://", u):
                    errors += fail(f"{rid}: {url_key} is not a URL -> {u}")

            for listk, lo in (("eligibility",2), ("documents",3), ("demoSteps",3)):
                if len(r.get(listk) or []) < lo:
                    errors += fail(f"{rid}: '{listk}' needs at least {lo} entries")
            fields = r.get("demoFields") or []
            if len(fields) < 5:
                errors += fail(f"{rid}: demoFields needs at least 5 entries")
            for f in fields:
                if not f.get("label") or not f.get("value"):
                    errors += fail(f"{rid}: a demoField is missing label or value")

            r.setdefault("state",""); r.setdefault("applyUrl","")
            r.setdefault("formUrl",""); r.setdefault("submitAt","")
            r.setdefault("portalName",""); r.setdefault("helpline","")
            r.setdefault("emoji","\U0001F4CB"); r.setdefault("colorHex","#2B52E0")
            r.setdefault("lastVerified","September 2026")
            schemes.append(r)

    order = {"Central":0, "State":1}
    schemes.sort(key=lambda r: (order.get(r["level"],2), r.get("state",""),
                                r.get("mode",""), r.get("category",""), r.get("title","")))

    json.dump({"schemes": schemes}, open(OUT,"w"), indent=1, ensure_ascii=False)

    from collections import Counter
    print(f"\nWrote {OUT} with {len(schemes)} schemes")
    print("  by level/mode:", dict(Counter(f"{r['level']}-{r['mode']}" for r in schemes)))
    print("  states:", dict(Counter(r["state"] for r in schemes if r["state"])))
    print("  categories:", dict(Counter(r["category"] for r in schemes)))
    print(f"\n{'VALIDATION PASSED' if errors == 0 else str(errors) + ' VALIDATION ERRORS'}")
    return 1 if errors else 0

sys.exit(main())
