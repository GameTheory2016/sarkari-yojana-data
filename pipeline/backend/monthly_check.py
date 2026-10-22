#!/usr/bin/env python3
"""The monthly check of every scheme's official pages.

    python3 backend/monthly_check.py            # check and report, change nothing
    python3 backend/monthly_check.py --apply    # also make the safe fixes and rebuild the data

What it does

1. It checks every applyUrl, portalUrl and formUrl in the English batches
   (Data/work/_part_*.json), using the forgiving curl client from
   Data/check_links.py.

2. It remembers results between runs in backend/state/links.json. A link
   counts as broken only after it is dead on two monthly runs in a row.
   Government sites are often down for a day, and some refuse connections
   from outside India, so one bad result proves nothing.

3. It compares each scheme's main page with last month's copy
   (backend/state/snapshots/). When the page text changed a lot, it flags the
   scheme for review, because that usually means a new amount, deadline or
   rule.

4. With --apply it makes only changes that cannot be wrong:
     - a deep link that failed twice falls back to the portal homepage,
     - a form-download link that failed twice is removed, so the button
       hides instead of opening an error page,
     - a permanent redirect within the same site, seen twice, is followed,
     - every scheme whose links all work gets this month as lastVerified,
   and then it rebuilds schemes_en.json and the 12 translations.

5. It writes backend/reports/YYYY-MM.md: what was fixed, and what a person
   (or the scheduled Claude task) has to research.

Nothing is published here. backend/publish.py does that.
"""
import argparse, concurrent.futures, datetime, difflib, glob, gzip, hashlib, html, json, os, re, subprocess, sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACK = os.path.join(ROOT, "backend")
WORK = os.path.join(ROOT, "Data", "work")
DATA = os.path.join(ROOT, "Resources", "data")
STATE = os.path.join(BACK, "state")
SNAP = os.path.join(STATE, "snapshots")
sys.path.insert(0, os.path.join(ROOT, "Data"))
sys.path.insert(0, BACK)
import check_links  # noqa: E402  classify() and the verdict names
import months       # noqa: E402

LANGS = ["gu", "hi", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "ur"]
KEYS = ("title,department,brief,benefit,portalName,submitAt,helpline,lastVerified,"
        "eligibility,documents,demoSteps,label,value,hint")
ITR = os.path.join(BACK, "itr", "scripts", "itr.py")
TM = os.path.join(BACK, "tm")
URL_FIELDS = ("applyUrl", "portalUrl", "formUrl")
SESSION = re.compile(r"(sid=|session|jsessionid|token=|viewstate)", re.I)
CHANGED_BELOW = 0.80   # page text similarity under this flags the scheme


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(p + ".tmp", p)


def records(data):
    return data["schemes"] if isinstance(data, dict) else data


def site(u):
    host = (urlparse(u).hostname or "").lower()
    parts = host.split(".")
    # Good enough for Indian government hosts: pmkisan.gov.in -> pmkisan.gov.in,
    # www.edistrict.wb.gov.in -> wb.gov.in.
    return ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ("gov", "nic", "co", "org", "ac") else ".".join(parts[-2:])


# ---- page text, for spotting changed rules --------------------------------

def page_text(url):
    cmd = ["curl", "-sL", "-k", "--http1.1", "-4", "--max-time", "25", "--max-filesize", "3000000",
           "-A", check_links.UA, url]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=40).stdout.decode("utf-8", "ignore")
    except subprocess.TimeoutExpired:
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    # Digits change every day on most portals (dates, visitor counters,
    # tokens) without the rules changing, so they are left out.
    text = re.sub(r"\d+", " ", text)
    return " ".join(text.split())[:60000]


def snapshot_path(url):
    return os.path.join(SNAP, hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt.gz")


def compare_page(url):
    """Return similarity with last month's text (None when there is no copy yet)."""
    text = page_text(url)
    if len(text) < 200:          # JavaScript shells and failures say nothing
        return None
    p = snapshot_path(url)
    ratio = None
    if os.path.exists(p):
        old = gzip.open(p, "rt", encoding="utf-8").read()
        ratio = difflib.SequenceMatcher(None, old.split(), text.split(), autojunk=False).ratio()
    os.makedirs(SNAP, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(text)
    return ratio


# ---- main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="make the safe fixes and rebuild the data")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--skip-pages", action="store_true", help="links only, no page comparison")
    a = ap.parse_args()

    today = datetime.date.today()
    month_key = today.strftime("%Y-%m")

    parts, before = {}, {}
    for f in sorted(glob.glob(os.path.join(WORK, "_part_*.json"))):
        parts[f] = load(f)
        before[f] = json.dumps(parts[f], sort_keys=True)
    schemes = {s["id"]: (f, s) for f, d in parts.items() for s in records(d)}

    urls = sorted({s[k] for _, s in schemes.values() for k in URL_FIELDS if s.get(k)})
    print(f"{len(schemes)} schemes, {len(urls)} links")
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        verdicts = dict(zip(urls, ex.map(check_links.classify, urls)))

    state = load(os.path.join(STATE, "links.json"), {})
    for u, (v, code, final) in verdicts.items():
        st = state.setdefault(u, {"dead": 0, "unreachable": 0, "redirect": 0})
        st["dead"] = st.get("dead", 0) + 1 if v == check_links.DEAD else 0
        st["unreachable"] = (st.get("unreachable", 0) + 1
                             if v in (check_links.UNREACHABLE, check_links.BLOCKED) else 0)
        same_move = v == check_links.REDIRECT and st.get("final") == final
        st["redirect"] = st.get("redirect", 0) + 1 if same_move else (1 if v == check_links.REDIRECT else 0)
        st.update(verdict=v, code=code, final=final, checked=today.isoformat())
        if v in (check_links.OK, check_links.REDIRECT):
            st["lastOk"] = today.isoformat()

    # Each scheme's main page: the portal homepage when there is one.
    changed = []
    if not a.skip_pages:
        mains = {}
        for sid, (_, s) in schemes.items():
            u = s.get("portalUrl") or s.get("applyUrl") or s.get("formUrl")
            if u and verdicts.get(u, (None,))[0] in (check_links.OK, check_links.REDIRECT):
                mains[sid] = u
        # Several schemes share one portal; each page is fetched once, or two
        # parallel fetches would compare against each other's snapshot.
        pages = sorted(set(mains.values()))
        with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
            by_url = dict(zip(pages, ex.map(compare_page, pages)))
        ratios = {sid: by_url[u] for sid, u in mains.items()}
        changed = sorted((sid, r) for sid, r in ratios.items() if r is not None and r < CHANGED_BELOW)

    fixes, review, verified = [], [], 0
    for sid, (f, s) in schemes.items():
        st = {k: state.get(s.get(k), {}) for k in URL_FIELDS if s.get(k)}
        portal_ok = st.get("portalUrl", {}).get("verdict") in (check_links.OK, check_links.REDIRECT)

        if st.get("applyUrl", {}).get("dead", 0) >= 2:
            if s.get("portalUrl") and portal_ok:
                fixes.append((sid, "deep link dead twice, now opens the portal homepage",
                              s["applyUrl"], s["portalUrl"]))
                if a.apply:
                    s["applyUrl"] = s.pop("portalUrl")
                    s.pop("applyKind", None)
            else:
                review.append((sid, "apply link dead twice and no working homepage", s.get("applyUrl")))
        # Hiding a download is harder to undo than falling back to a
        # homepage, and a 404 can come from a site that refuses foreign
        # visitors, so a form link has to be dead three months running.
        if st.get("formUrl", {}).get("dead", 0) >= 3:
            fixes.append((sid, "form download dead three months running, button hidden", s["formUrl"], ""))
            if a.apply:
                s["formUrl"] = ""
        for k, ks in st.items():
            if ks.get("unreachable", 0) >= 3:
                review.append((sid, f"{k} unreachable three months running", s.get(k)))
            # A redirect that still lands is not broken, so it is left alone,
            # except when the site moved to a new host name within the same
            # government domain (aasara.telangana.gov.in -> cheyutha.telangana.gov.in).
            # The old name may stop redirecting one day.
            fin = ks.get("final", "")
            old_host = (urlparse(s.get(k, "")).hostname or "").lower().removeprefix("www.")
            new_host = (urlparse(fin).hostname or "").lower().removeprefix("www.")
            if (ks.get("redirect", 0) >= 2 and fin and "?" not in fin and not SESSION.search(fin)
                    and site(fin) == site(s.get(k, "")) and old_host != new_host):
                fixes.append((sid, f"{k} moved within the same site", s.get(k), fin))
                if a.apply:
                    s[k] = fin

        if all(ks.get("verdict") in (check_links.OK, check_links.REDIRECT) for ks in st.values()):
            verified += 1
            if a.apply:
                s["lastVerified"] = months.english(today.year, today.month)

    for sid, r in changed:
        review.append((sid, f"official page changed (similarity {r:.0%}); check amounts, dates and rules",
                       schemes[sid][1].get("portalUrl") or schemes[sid][1].get("applyUrl")))

    dump(state, os.path.join(STATE, "links.json"))

    counts = {}
    for v, _, _ in verdicts.values():
        counts[v] = counts.get(v, 0) + 1
    lines = [f"# Monthly check {month_key}", "",
             f"- Schemes: {len(schemes)}; links: {len(urls)}",
             f"- Link results: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())),
             f"- Schemes with every link working: {verified}",
             f"- Fixes {'applied' if a.apply else 'proposed (run with --apply)'}: {len(fixes)}",
             f"- Need research: {len(review)}", ""]
    if fixes:
        lines += ["## Fixes", ""] + [f"- `{sid}`: {why}  \n  {old} → {new or '(removed)'}"
                                     for sid, why, old, new in fixes] + [""]
    if review:
        lines += ["## Needs research", "",
                  "Open the link, compare with the scheme's text in Data/work, and update the English "
                  "record if anything changed. Then run the translation step in backend/README.md.", ""]
        lines += [f"- `{sid}`: {why}  \n  {u}" for sid, why, u in review] + [""]
    report = os.path.join(BACK, "reports", f"{month_key}.md")
    os.makedirs(os.path.dirname(report), exist_ok=True)
    open(report, "w", encoding="utf-8").write("\n".join(lines))
    dump({"month": month_key, "counts": counts, "verified": verified,
          "fixes": [dict(id=i, why=w, old=o, new=n) for i, w, o, n in fixes],
          "review": [dict(id=i, why=w, url=u) for i, w, u in review]},
         os.path.join(BACK, "reports", f"{month_key}.json"))
    print("\n".join(lines[:8]))
    print(f"report: {report}")

    if a.apply:
        # Only batches that really changed are rewritten.
        for f, d in parts.items():
            if json.dumps(d, sort_keys=True) != before[f]:
                dump(d, f)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "Data", "merge_schemes.py")],
                           capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr)
        if r.returncode != 0:
            print("merge_schemes.py failed; translations were not rebuilt")
            return 1
        return rebuild_translations(today)
    return 0


def rebuild_translations(today):
    """Put this month's date into the memory, then rebuild all 12 files."""
    for lang in LANGS:
        tm_file = os.path.join(TM, f"{lang}.json")
        tm = load(tm_file, {})
        en = months.english(today.year, today.month)
        tm[hashlib.sha1(en.encode()).hexdigest()[:12]] = {"en": en, "t": months.local(lang, today.year, today.month)}
        dump(tm, tm_file)
    src = os.path.join(DATA, "schemes_en.json")
    r = subprocess.run([sys.executable, ITR, "apply", "--src", src, "--keys", KEYS,
                        "--langs", ",".join(LANGS), "--tm", TM, "--work", os.path.join(BACK, "work"),
                        "--out", os.path.join(DATA, "schemes_{lang}.json"), "--overlay"],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    missing = [l for l in r.stdout.splitlines() if "still English" in l and " 0 still English" not in l]
    if missing:
        print("\nSome English text has no translation yet. Follow 'Translating changed text' "
              "in backend/README.md before publishing.")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
