#!/usr/bin/env python3
"""Check every government link in the catalogue and say which ones moved or died.

Usage:
    python3 Data/check_links.py                       # check schemes_en.json
    python3 Data/check_links.py --json report.json    # also write a report
    python3 Data/check_links.py --only gj-ikhedut     # one scheme

Indian government sites need a forgiving client. Many still negotiate badly
over HTTP/2, some have a broken certificate chain, and roughly one host in ten
refuses connections from outside India altogether. A refusal from a machine
abroad is therefore not proof that a link is dead, so those are reported
separately from real 404s and never fail the run on their own.

Exit code is 1 when a link is DEAD, 0 otherwise, so a scheduled job can open an
issue only when something genuinely needs fixing.
"""
import argparse, concurrent.futures, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "Resources", "data")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

URL_FIELDS = ("applyUrl", "formUrl", "portalUrl")

# Verdicts, worst last — the summary is printed in this order.
OK, REDIRECT, BLOCKED, UNREACHABLE, DEAD = "OK", "REDIRECT", "BLOCKED", "UNREACHABLE", "DEAD"


def curl(url, insecure=False, timeout=25):
    """One attempt. Returns (http_code, final_url, curl_exit)."""
    cmd = ["curl", "-sS", "-o", "/dev/null", "-L", "--http1.1", "-4",
           "--max-time", str(timeout), "-A", UA,
           "-w", "%{http_code} %{url_effective}"]
    if insecure:
        cmd.append("-k")
    cmd.append(url)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        return 0, url, 28
    out = (p.stdout or "").strip().split(" ", 1)
    code = int(out[0]) if out and out[0].isdigit() else 0
    final = out[1] if len(out) > 1 else url
    return code, final, p.returncode


def classify(url):
    """Check one URL over up to two passes and return (verdict, code, final)."""
    code, final, rc = curl(url)
    if rc != 0 or code == 0:
        # A bad certificate chain is common on state portals and is not a dead
        # link, so try again without verification before giving up.
        code, final, rc = curl(url, insecure=True)

    if code == 0:
        # 6 unknown host, 7 refused, 28 timeout, 35 TLS handshake.
        return (UNREACHABLE if rc in (6, 28) else BLOCKED), code, final
    if code in (403, 406, 451):
        return BLOCKED, code, final
    if code in (404, 410):
        return DEAD, code, final
    if code >= 500:
        return UNREACHABLE, code, final
    # A site that answers 200 while redirecting you to its own error page is
    # broken, not working. Odisha's Bhulekh does exactly this, and counting it
    # as a mere redirect hid a link that led nowhere.
    if re.search(r"(error|404|notfound|not[-_]found)", final, re.I) and \
       not re.search(r"(error|404)", url, re.I):
        return DEAD, code, final

    # Compare ignoring a trailing slash and the scheme, so http -> https or
    # example.gov.in -> example.gov.in/ is not reported as a move.
    def norm(u):
        return re.sub(r"^https?://", "", u.strip()).rstrip("/").lower()
    return (OK if norm(final) == norm(url) else REDIRECT), code, final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(DATA, "schemes_en.json"))
    ap.add_argument("--json", help="write the full report here")
    ap.add_argument("--only", help="check one scheme id")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    schemes = json.load(open(args.file))["schemes"]
    if args.only:
        schemes = [s for s in schemes if s["id"] == args.only]
        if not schemes:
            print(f"no scheme with id '{args.only}'"); return 2

    targets = [(s["id"], f, s[f]) for s in schemes for f in URL_FIELDS if s.get(f)]
    print(f"checking {len(targets)} links from {len(schemes)} schemes, "
          f"{args.jobs} at a time\n")

    results = []
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(classify, url): (sid, field, url)
                   for sid, field, url in targets}
        for done in concurrent.futures.as_completed(futures):
            sid, field, url = futures[done]
            verdict, code, final = done.result()
            results.append({"id": sid, "field": field, "url": url,
                            "verdict": verdict, "code": code, "final": final})
            if verdict != OK:
                print(f"  {verdict:<11} {code:>3}  {sid} ({field})\n"
                      f"              {url}"
                      + (f"\n           -> {final}" if verdict == REDIRECT else ""))

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    print(f"\nchecked {len(results)} links in {time.time()-started:.0f}s")
    for v in (OK, REDIRECT, BLOCKED, UNREACHABLE, DEAD):
        if counts.get(v):
            print(f"  {v:<12} {counts[v]}")

    if args.json:
        json.dump({"checked": len(results),
                   "counts": counts,
                   "results": sorted(results, key=lambda r: (r["verdict"], r["id"]))},
                  open(args.json, "w"), indent=1)
        print(f"\nreport written to {args.json}")

    if counts.get(DEAD):
        print(f"\n{counts[DEAD]} dead link(s) — these need fixing before a release.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
