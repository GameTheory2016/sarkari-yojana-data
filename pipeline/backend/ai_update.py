#!/usr/bin/env python3
"""Update schemes whose official page changed, then translate what changed.

    GEMINI_API_KEY=... python3 backend/ai_update.py                    # monthly: content + translation
    GEMINI_API_KEY=... python3 backend/ai_update.py --translate-only   # daily: translation only

This runs after `monthly_check.py --apply`, whose report says which schemes'
pages changed. It uses Google's Gemini API on the free tier, which needs no
card. Without GEMINI_API_KEY it does nothing, and the month still publishes
its link fixes.

A change is made only when all of these hold:
  * the model quotes the official page word for word as evidence, and that
    quote really is in the page text we fetched,
  * every number in the new text that was not in the old text appears in
    that quote,
  * the field is one a citizen reads (brief, benefit, eligibility, documents,
    demoSteps, submitAt, helpline). Ids, links and categories are never
    touched,
  * no more than MAX_SCHEMES schemes change in one month.
Anything else stays as it was and is listed in the report. A scheme is never
deleted automatically, even when the model thinks it has ended.

The changed English text then goes through the translation memory (itr): only
new sentences go to the model, and itr rejects any translation that loses a
number, link or placeholder, or comes back in the wrong script.
"""
import datetime, glob, html, json, os, re, subprocess, sys, time
import urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACK = os.path.join(ROOT, "backend")
WORK = os.path.join(ROOT, "Data", "work")
DATA = os.path.join(ROOT, "Resources", "data")
ITR = os.path.join(BACK, "itr", "scripts", "itr.py")
TM = os.path.join(BACK, "tm")
ITR_WORK = os.path.join(BACK, "work")
LANGS = ["gu", "hi", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "ur"]
KEYS = ("title,department,brief,benefit,portalName,submitAt,helpline,lastVerified,"
        "eligibility,documents,demoSteps,label,value,hint")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Empty means: pick the newest Flash model the key can use (Google retires
# old models, and a fixed name would stop the pipeline one day).
MODEL = os.environ.get("GEMINI_MODEL", "")
KEY = os.environ.get("GEMINI_API_KEY", "")
MAX_SCHEMES = 15
# The free tier allows a few hundred requests a day. Each run stops here and
# the next daily run carries on; itr remembers what is already done.
MAX_REQUESTS = int(os.environ.get("GEMINI_MAX_REQUESTS", "180"))
_requests = 0
GEMINI_ORDER = "as or pa ml kn ta bn mr gu hi te ur".split()
# The workflow is killed after 300 minutes, losing everything; stop well before.
DEADLINE = time.time() + 60 * float(os.environ.get("GEMINI_MAX_MINUTES", "200"))
TEXT_FIELDS = ("brief", "benefit", "submitAt", "helpline")
LIST_FIELDS = ("eligibility", "documents", "demoSteps")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


# ---- helpers ---------------------------------------------------------------

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


def norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―]", "-", s)
    return " ".join(s.lower().split())


def numbers(s):
    return {n.replace(",", "") for n in NUM.findall(s or "")}


def fetch_text(url):
    """Visible text of a page, digits kept, because evidence needs them."""
    cmd = ["curl", "-sL", "-k", "--http1.1", "-4", "--max-time", "30", "--max-filesize", "4000000",
           "-A", UA, url]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=45).stdout.decode("utf-8", "ignore")
    except subprocess.TimeoutExpired:
        return ""
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    return " ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)).split())


_candidates = None  # usable models, best first; filled on first use
FLASH = re.compile(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?(-preview[\w-]*|-\d{3})?")


def next_model(dead=None):
    """The best Flash model still worth trying: stable before preview, newest first."""
    global _candidates
    if _candidates is None:
        names = []
        try:
            req = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                headers={"x-goog-api-key": KEY})
            with urllib.request.urlopen(req, timeout=60) as r:
                for m in json.load(r).get("models", []):
                    n = m["name"].split("/")[-1]
                    if (FLASH.fullmatch(n)
                            and "generateContent" in m.get("supportedGenerationMethods", [])):
                        names.append(n)
        except Exception as e:
            print(f"  Gemini model list failed: {e}")
        # Each model has its own free daily quota, so the lite ones are a fallback.
        names.sort(key=lambda n: ("lite" not in n, "preview" not in n,
                                  [int(x) for x in FLASH.fullmatch(n)[1].split(".")]),
                   reverse=True)
        _candidates = ([MODEL] if MODEL else []) + names + ["gemini-flash-latest"]
    _candidates = [c for c in _candidates if c != dead]
    return _candidates[0] if _candidates else None


def gemini(prompt, retries=4):
    """One JSON answer from Gemini, or None. Paced for the free tier."""
    global _requests, MODEL
    if time.time() > DEADLINE:
        _requests = MAX_REQUESTS
    if _requests >= MAX_REQUESTS:
        return None
    if not MODEL:
        MODEL = next_model()
        print(f"  using {MODEL}")
    if not MODEL or MODEL == "none":
        return None
    _requests += 1
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json",
                                            "temperature": 0.2}}).encode()
    attempt = 0
    while attempt < retries:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "x-goog-api-key": KEY})
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                data = json.load(r)
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:
            msg = e.read()[:3000]
            if e.code == 404 or (e.code == 429 and b"limit: 0" in msg):
                # Retired, or no free quota on this model: move to the next one.
                MODEL = next_model(MODEL) or "none"
                print(f"  Gemini HTTP {e.code}; switching to {MODEL}")
                if MODEL == "none":
                    return None
                continue
            if e.code == 429 and b"PerDay" in msg:
                # This model's free quota for today is used up; try the next one.
                MODEL = next_model(MODEL) or "none"
                print(f"  Gemini daily quota reached; switching to {MODEL}")
                if MODEL != "none":
                    continue
            if e.code == 429 and (MODEL == "none" or attempt == retries - 1):
                # Nothing left for today: stop, so the run ends quickly and
                # commits what it has; tomorrow's run carries on.
                print("  stopping for today")
                _requests = MAX_REQUESTS
                return None
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(40 * (attempt + 1))
                attempt += 1
                continue
            print(f"  Gemini HTTP {e.code}: {msg[:300]}")
            return None
        except Exception as e:  # network, malformed answer
            if attempt < retries - 1:
                time.sleep(15)
                attempt += 1
                continue
            print(f"  Gemini failed: {e}")
            return None
        finally:
            time.sleep(7)  # the free tier allows about ten requests a minute
    return None


# ---- step 1: content changes -----------------------------------------------

PROMPT = """You keep an app accurate. The app explains Indian government schemes to ordinary
citizens, many elderly or with little schooling. Below are our current English record
for one scheme and the current text of its official web page.

Decide whether the page shows that any of these facts has CHANGED compared with our
record: the benefit or amount, who is eligible, the documents needed, the application
steps, where to submit the form, or the helpline.

Rules:
- Report a change only when the page states the new fact explicitly. If unsure, do
  not report it.
- Ignore wording differences, layout, news, event dates and notices that are not about
  the scheme's rules.
- For each change, "evidence" must be an exact quote copied character for character
  from the page text (20 to 300 characters) that states the new fact.
- Write "new" in our style: plain, short English for an ordinary citizen. Keep every
  number exactly as the page gives it.
- For eligibility, documents and demoSteps, "index" is the 0-based item to replace,
  or -1 to add a new item. For the other fields, use index -1.

Return only JSON:
{{"changes": [{{"field": "brief|benefit|submitAt|helpline|eligibility|documents|demoSteps",
  "index": -1, "new": "...", "evidence": "..."}}],
 "scheme_ended": false, "ended_evidence": ""}}

OUR RECORD:
{record}

OFFICIAL PAGE ({url}):
{page}
"""


def check_change(c, rec, page_n):
    """Return (ok, reason)."""
    field, new, ev = c.get("field"), (c.get("new") or "").strip(), (c.get("evidence") or "").strip()
    if field not in TEXT_FIELDS + LIST_FIELDS:
        return False, f"field '{field}' is not allowed"
    if not new or len(new) > 700:
        return False, "new text empty or too long"
    if len(ev) < 15 or norm(ev) not in page_n:
        return False, "evidence is not on the official page"
    if field in LIST_FIELDS:
        idx = c.get("index", -1)
        if not isinstance(idx, int) or idx < -1 or idx >= len(rec.get(field) or []):
            return False, "bad list index"
        old = rec[field][idx] if idx >= 0 else ""
    else:
        old = rec.get(field) or ""
    if norm(new) == norm(old):
        return False, "no real change"
    missing = numbers(new) - numbers(old) - numbers(ev)
    if missing:
        return False, f"numbers {sorted(missing)} are not in the evidence"
    return True, ""


def update_content(month):
    report = load(os.path.join(BACK, "reports", f"{month}.json"), {})
    flagged = [r["id"] for r in report.get("review", []) if r["why"].startswith("official page changed")]
    if not flagged:
        print("no changed pages this month")
        return [], []
    parts = {f: load(f) for f in sorted(glob.glob(os.path.join(WORK, "_part_*.json")))}
    where = {s["id"]: (f, s) for f, d in parts.items() for s in records(d)}

    applied, skipped, dirty = [], [], set()
    for sid in flagged[:MAX_SCHEMES]:
        if sid not in where:
            continue
        f, rec = where[sid]
        url = rec.get("portalUrl") or rec.get("applyUrl") or rec.get("formUrl")
        page = fetch_text(url)
        if len(page) < 300:
            skipped.append((sid, "page could not be read", ""))
            continue
        view = {k: rec.get(k) for k in ("title",) + TEXT_FIELDS + LIST_FIELDS if rec.get(k)}
        ans = gemini(PROMPT.format(record=json.dumps(view, ensure_ascii=False, indent=1),
                                   url=url, page=page[:20000]))
        if not isinstance(ans, dict):
            skipped.append((sid, "no answer from the model", ""))
            continue
        page_n = norm(page)
        added = {}
        for c in ans.get("changes") or []:
            ok, why = check_change(c, rec, page_n)
            if ok and c["field"] in LIST_FIELDS and c.get("index", -1) == -1:
                added[c["field"]] = added.get(c["field"], 0) + 1
                if added[c["field"]] > 2:
                    ok, why = False, "more than two new items in one list"
            if not ok:
                skipped.append((sid, why, c.get("new", "")[:120]))
                continue
            field, new = c["field"], c["new"].strip()
            if field in LIST_FIELDS:
                if c.get("index", -1) == -1:
                    rec.setdefault(field, []).append(new)
                else:
                    rec[field][c["index"]] = new
            else:
                rec[field] = new
            applied.append((sid, field, new, c["evidence"][:200], url))
            dirty.add(f)
        if ans.get("scheme_ended") and norm(ans.get("ended_evidence", "")) in page_n:
            skipped.append((sid, "the model thinks this scheme ended (not removed automatically)",
                            ans.get("ended_evidence", "")[:200]))
    for f in dirty:
        dump(parts[f], f)
    if dirty:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "Data", "merge_schemes.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("merge_schemes.py failed after AI edits:\n" + r.stdout[-1500:])
            sys.exit(1)
    return applied, skipped


# ---- step 2: translate whatever is new ---------------------------------------

def itr(*args):
    return subprocess.run([sys.executable, ITR, *args], capture_output=True, text=True)


def translate_new_text():
    src = os.path.join(DATA, "schemes_en.json")
    for attempt in range(2):  # a second pass resends anything itr rejected
        r = itr("extract", "--src", src, "--keys", KEYS, "--langs", ",".join(LANGS),
                "--tm", TM, "--work", ITR_WORK)
        # Claude agents translate from the most-read languages down, so this
        # starts at the other end.
        todos = sorted(glob.glob(os.path.join(ITR_WORK, "*", "todo_*.json")),
                       key=lambda t: (GEMINI_ORDER.index(os.path.basename(os.path.dirname(t)))
                                      if os.path.basename(os.path.dirname(t)) in GEMINI_ORDER
                                      else 99, t))
        if not todos:
            break
        print(f"translating {len(todos)} chunks (pass {attempt + 1})")
        for t in todos:
            if _requests >= MAX_REQUESTS:
                print(f"stopping at the daily limit of {MAX_REQUESTS} requests; the next run carries on")
                break
            chunk = load(t)
            prompt = (chunk["instructions"] +
                      "\n\nReturn only JSON in the form {\"items\": [{\"k\": \"...\", \"t\": \"...\"}]}.\n\n"
                      "ITEMS:\n" + json.dumps(chunk["items"], ensure_ascii=False))
            ans = gemini(prompt)
            if isinstance(ans, dict) and isinstance(ans.get("items"), list):
                dump({"items": ans["items"]}, chunk["write_to"])
    r = itr("apply", "--src", src, "--keys", KEYS, "--langs", ",".join(LANGS), "--tm", TM,
            "--work", ITR_WORK, "--out", os.path.join(DATA, "schemes_{lang}.json"), "--overlay")
    print(r.stdout.strip())


# ---- main ------------------------------------------------------------------

def main():
    if not KEY:
        print("GEMINI_API_KEY is not set; skipping AI updates")
        return 0
    month = datetime.date.today().strftime("%Y-%m")
    if "--translate-only" in sys.argv:
        translate_new_text()
        return 0
    applied, skipped = update_content(month)
    translate_new_text()

    lines = ["", "## AI updates", "",
             f"Model: {MODEL}. Changed: {len(applied)}. Not changed: {len(skipped)}.", ""]
    lines += [f"- `{sid}` {field}: {new}  \n  evidence: \"{ev}\"  \n  {url}"
              for sid, field, new, ev, url in applied]
    if skipped:
        lines += ["", "Left as they were:", ""]
        lines += [f"- `{sid}`: {why}" + (f" ({txt})" if txt else "") for sid, why, txt in skipped]
    md = os.path.join(BACK, "reports", f"{month}.md")
    with open(md, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    js = os.path.join(BACK, "reports", f"{month}.json")
    rep = load(js, {})
    rep["ai"] = {"model": MODEL,
                 "applied": [dict(id=a, field=b, new=c, evidence=d, url=e) for a, b, c, d, e in applied],
                 "skipped": [dict(id=a, why=b, text=c) for a, b, c in skipped]}
    dump(rep, js)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
