#!/usr/bin/env python3
"""itr: translation memory, chunking and checks for Indian-language JSON.

    python3 itr.py scan    --src en.json
    python3 itr.py seed    --src en.json --keys K --lang hi --translated hi.json --tm TM
    python3 itr.py seed    --lang hi --terms common_terms/hi.json --tm TM
    python3 itr.py extract --src en.json --keys K --langs hi,gu --tm TM --work WORK
    python3 itr.py apply   --src en.json --keys K --langs hi,gu --tm TM --work WORK \
                           --out 'data/strings_{lang}.json' [--overlay]
    python3 itr.py status  --src en.json --keys K --langs hi,gu --tm TM
    python3 itr.py terms   --src en.json --keys K --langs hi,gu --tm TM --out DIR

How it saves tokens
  * Every string is keyed by its English text (sha1). A sentence used 200
    times is translated once. One translated last month is never sent again.
    Changing one sentence re-sends one sentence.
  * Ids, URLs, e-mail addresses and values with no letters are never sent.
  * Each chunk file carries its own instructions, so a translator agent needs
    one Read and one Write. Every extra tool call makes the agent re-read its
    whole context, and that re-reading is most of what an agent costs.

--keys is a comma list of key names whose string values (or lists of strings)
are text a reader sees. Use '*' for a flat {"key": "text"} UI-strings file.
Run `scan` first to see which keys exist.

Only the Python 3 standard library is used.
"""
import argparse, collections, glob, hashlib, json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "references")

# code: (English name, script name, Unicode ranges, words per chunk)
# Words per chunk is sized so the translated output stays under one
# response's output limit. Dravidian scripts, Gurmukhi and Odia cost more
# tokens per word, and Kannada and Punjabi agents hit the limit at about
# 5,000 source words, so they get smaller chunks.
DEVA = [(0x0900, 0x097F), (0xA8E0, 0xA8FF)]
BENG = [(0x0980, 0x09FF)]
ARAB = [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
LANGS = {
    "hi": ("Hindi", "Devanagari", DEVA, 4000),
    "mr": ("Marathi", "Devanagari", DEVA, 4000),
    "gu": ("Gujarati", "Gujarati", [(0x0A80, 0x0AFF)], 4000),
    "bn": ("Bengali", "Bengali", BENG, 4000),
    "as": ("Assamese", "Bengali (Assamese)", BENG, 3500),
    "pa": ("Punjabi", "Gurmukhi", [(0x0A00, 0x0A7F)], 3000),
    "or": ("Odia", "Odia", [(0x0B00, 0x0B7F)], 3000),
    "ta": ("Tamil", "Tamil", [(0x0B80, 0x0BFF)], 3000),
    "te": ("Telugu", "Telugu", [(0x0C00, 0x0C7F)], 3000),
    "kn": ("Kannada", "Kannada", [(0x0C80, 0x0CFF)], 3000),
    "ml": ("Malayalam", "Malayalam", [(0x0D00, 0x0D7F)], 3000),
    "ur": ("Urdu", "Perso-Arabic (Nastaliq)", ARAB, 4000),
    "kok": ("Konkani", "Devanagari", DEVA, 3500),
    "ne": ("Nepali", "Devanagari", DEVA, 3500),
    "mai": ("Maithili", "Devanagari", DEVA, 3500),
    "doi": ("Dogri", "Devanagari", DEVA, 3500),
    "brx": ("Bodo", "Devanagari", DEVA, 3500),
    "ks": ("Kashmiri", "Perso-Arabic", ARAB, 3500),
    "sd": ("Sindhi", "Perso-Arabic or Devanagari", ARAB + DEVA, 3500),
    "mni": ("Manipuri (Meitei)", "Bengali or Meetei Mayek", BENG + [(0xABC0, 0xABFF), (0xAAE0, 0xAAFF)], 3000),
    "sat": ("Santali", "Ol Chiki", [(0x1C50, 0x1C7F)], 3000),
    "lus": ("Mizo", "Latin", [], 4000),
    "kha": ("Khasi", "Latin", [], 4000),
    "grt": ("Garo", "Latin", [], 4000),
    "trp": ("Kokborok", "Latin or Bengali", BENG, 4000),
    "en": ("English", "Latin", [], 4000),
}

URL = re.compile(r"^(https?://|www\.)\S+$|^[\w.+-]+@[\w-]+(\.[\w-]+)+$", re.I)
# Things a translation must carry over unchanged: format placeholders, markup,
# escaped newlines, links, e-mail addresses. A link ends at the first
# non-ASCII character, because Bengali and Tamil attach case endings straight
# onto it ("login-এ").
PH = re.compile(r"\{[^{}]*\}|%(?:\d+\$)?[sdfi@]|</?[a-zA-Z][^>]*>|\\n|"
                r"https?://[!-~]+|www\.[!-~]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.A)
NUM = re.compile(r"\d[\d,]*(?:[.:/-]\d+)*")


def h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def has_letters(s):
    return any(unicodedata.category(c).startswith("L") for c in s)


def text_words(s):
    """Ordinary words in an English string: no links, e-mails, placeholders,
    ALL-CAPS acronyms or tokens with digits. "98765 43210 / a.b@example.com"
    and "IFSC SBIN0000999" have none, so they are kept as they are."""
    return re.findall(r"(?<![\w@.])[A-Za-z][a-z]+(?:['’][a-z]+)?(?![\w@])", PH.sub(" ", s))


def wanted(value, key, keys):
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or not has_letters(v) or URL.match(v):
        return False
    if v.isascii() and not text_words(v):
        return False
    return "*" in keys or key in keys


def walk(node, keys, key=None, path=()):
    """Yield (path, key, text) for every translatable string, in order."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, keys, k, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, keys, key, path + (i,))
    elif wanted(node, key, keys):
        yield path, key, node


def set_path(node, path, value):
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value


def parse_keys(s):
    return set(k.strip() for k in s.split(",") if k.strip())


def lang_info(code):
    if code not in LANGS:
        sys.exit(f"unknown language '{code}'. Known: {', '.join(sorted(LANGS))}")
    return LANGS[code]


# ---- translation memory ----------------------------------------------------

def tm_path(tm_dir, lang):
    return os.path.join(tm_dir, f"{lang}.json")


def tm_load(tm_dir, lang):
    p = tm_path(tm_dir, lang)
    return load(p) if os.path.exists(p) else {}


def tm_save(tm_dir, lang, tm):
    dump(dict(sorted(tm.items(), key=lambda kv: kv[1]["en"].lower())), tm_path(tm_dir, lang))


# ---- checks ----------------------------------------------------------------

def protected(s):
    """Placeholders, links and markup, with trailing punctuation dropped so
    "see www.x.org," and "www.x.org पर देखें" compare equal."""
    return collections.Counter(m.rstrip(".,;:!?।-)]\"'") for m in PH.findall(s))


def in_ranges(c, ranges):
    o = ord(c)
    return any(a <= o <= b for a, b in ranges)


def check(en, tr, lang):
    """Return (errors, warnings) for one translated string."""
    errors, warns = [], []
    if not isinstance(tr, str) or not tr.strip():
        return ["empty"], []
    if protected(en) != protected(tr):
        errors.append("placeholder, link or markup changed")
    a = collections.Counter(n.replace(",", "") for n in NUM.findall(en))
    b = collections.Counter(n.replace(",", "") for n in NUM.findall(tr))
    if a != b:
        long_a = {n for n in a if len(re.sub(r"\D", "", n)) >= 5}
        long_b = {n for n in b if len(re.sub(r"\D", "", n)) >= 5}
        # Phone numbers, ids and account numbers must survive exactly.
        (errors if long_a != long_b else warns).append(f"numbers differ {sorted(a)} vs {sorted(b)}")
    ranges = LANGS[lang][2]
    words = text_words(en)
    # Short strings are often names a translator rightly keeps in Latin
    # ("Sewa Setu Assam"), so only sentences must be in the target script.
    if ranges and len(words) >= 3:
        native = sum(1 for c in tr if in_ranges(c, ranges))
        if native == 0:
            (errors if len(words) >= 6 else warns).append(f"no {LANGS[lang][1]} letters in it")
        else:
            other = sum(1 for c in tr if ord(c) > 0x2FF and unicodedata.category(c).startswith("L")
                        and not in_ranges(c, ranges))
            if other > native * 0.1:
                warns.append("letters from another script mixed in")
    if lang != "en" and tr.strip() == en.strip() and len(words) >= 6:
        errors.append("left in English")
    return errors, warns


# ---- commands --------------------------------------------------------------

def cmd_scan(a):
    src = load(a.src)
    stats = collections.OrderedDict()

    def rec(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                rec(v, k)
        elif isinstance(node, list):
            for v in node:
                rec(v, key)
        elif isinstance(node, str):
            s = stats.setdefault(key, {"n": 0, "words": 0, "sample": "", "text": 0})
            s["n"] += 1
            if has_letters(node) and not URL.match(node.strip()):
                s["text"] += 1
                s["words"] += len(node.split())
                if not s["sample"]:
                    s["sample"] = node[:70]
    rec(src)
    print(f"{'key':<22}{'strings':>8}{'texty':>7}{'words':>8}  sample")
    for k, s in sorted(stats.items(), key=lambda kv: -kv[1]["words"]):
        print(f"{str(k):<22}{s['n']:>8}{s['text']:>7}{s['words']:>8}  {s['sample']}")
    print("\nPick the keys a reader actually sees. Leave out ids, enum values the code"
          "\ncompares against (category, mode, level, state codes), colours and links.")


def align(en, tr, keys, key, out):
    """Walk an English tree and its translation side by side."""
    if isinstance(en, dict) and isinstance(tr, dict):
        for k, v in en.items():
            if k in tr:
                align(v, tr[k], keys, k, out)
    elif isinstance(en, list) and isinstance(tr, list):
        if en and all(isinstance(x, dict) and "id" in x for x in en):
            by_id = {x.get("id"): x for x in tr if isinstance(x, dict)}
            for x in en:
                if x["id"] in by_id:
                    align(x, by_id[x["id"]], keys, key, out)
        else:
            for x, y in zip(en, tr):
                align(x, y, keys, key, out)
    elif wanted(en, key, keys) and isinstance(tr, str):
        out.append((en, tr))


def cmd_seed(a):
    lang_info(a.lang)
    tm = tm_load(a.tm, a.lang)
    added = bad = 0
    pairs = []
    if a.terms:
        data = load(a.terms)
        if isinstance(data, dict) and all(isinstance(v, dict) and "en" in v for v in data.values()):
            pairs = [(v["en"], v["t"]) for v in data.values()]
        else:
            pairs = list(data.items())
    if a.translated:
        if not a.src or not a.keys:
            sys.exit("--translated needs --src and --keys")
        align(load(a.src), load(a.translated), parse_keys(a.keys), None, pairs)
    for en, tr in pairs:
        errs, _ = check(en, tr, a.lang)
        if errs:
            bad += 1
            continue
        k = h(en)
        if k not in tm:
            tm[k] = {"en": en, "t": tr}
            added += 1
    tm_save(a.tm, a.lang, tm)
    print(f"{a.lang}: {added} added, {bad} skipped by checks, memory now {len(tm)}")


def instructions(lang):
    general = open(os.path.join(REF, "general_rules.md"), encoding="utf-8").read()
    langs = open(os.path.join(REF, "languages.md"), encoding="utf-8").read()
    m = re.search(rf"^## .*\({re.escape(lang)}\)\s*$(.*?)(?=^## |\Z)", langs, re.M | re.S)
    section = m.group(0).strip() if m else f"## {LANGS[lang][0]} ({lang})\nNo notes yet."
    return general.strip() + "\n\n" + section


def ingest(work, tm_dir, lang, verbose=True):
    """Fold finished chunk files into the memory. Returns (good, bad)."""
    d = os.path.join(work, lang)
    good = bad = 0
    tm = tm_load(tm_dir, lang)
    for todo_path in sorted(glob.glob(os.path.join(d, "todo_*.json"))):
        done_path = todo_path.replace("todo_", "done_")
        if not os.path.exists(done_path):
            continue
        todo = {it["k"]: it["t"] for it in load(todo_path)["items"]}
        try:
            done = load(done_path)
        except Exception as e:
            print(f"  {os.path.basename(done_path)}: not valid JSON ({e}); it will be sent again")
            continue
        items = done.get("items", done) if isinstance(done, dict) else done
        for it in items:
            k, tr = it.get("k"), it.get("t")
            if k not in todo:
                continue
            errs, warns = check(todo[k], tr, lang)
            if errs:
                bad += 1
                if verbose:
                    print(f"  rejected {k}: {'; '.join(errs)}\n    en: {todo[k][:90]}\n    tr: {str(tr)[:90]}")
                continue
            if warns and verbose:
                print(f"  warning {k}: {'; '.join(warns)}")
            tm[h(todo[k])] = {"en": todo[k], "t": tr}
            good += 1
    tm_save(tm_dir, lang, tm)
    return good, bad


def pending(src, keys, tm):
    seen, out = set(), []
    for _, key, text in walk(src, keys):
        k = h(text)
        if k in tm or k in seen:
            continue
        seen.add(k)
        out.append((k, key, text))
    return out


def cmd_extract(a):
    src, keys = load(a.src), parse_keys(a.keys)
    total = collections.OrderedDict()
    for _, _, t in walk(src, keys):
        total.setdefault(h(t), t)
    all_words = sum(len(t.split()) for t in total.values())
    print(f"source: {len(total)} unique strings, {all_words} words\n")
    jobs = []
    for lang in a.langs.split(","):
        name, script, _, budget = lang_info(lang)
        budget = a.words or budget
        g, b = ingest(a.work, a.tm, lang)
        tm = tm_load(a.tm, lang)
        d = os.path.join(a.work, lang)
        for f in glob.glob(os.path.join(d, "todo_*.json")) + glob.glob(os.path.join(d, "done_*.json")):
            os.remove(f)
        todo = pending(src, keys, tm)
        words = sum(len(t.split()) for _, _, t in todo)
        chunks, cur, cw = [], [], 0
        for k, key, text in todo:
            n = len(text.split())
            if cur and (cw + n > budget or len(cur) >= 400):
                chunks.append(cur)
                cur, cw = [], 0
            cur.append({"k": k, "ctx": key, "t": text})
            cw += n
        if cur:
            chunks.append(cur)
        rules = instructions(lang)
        for i, items in enumerate(chunks, 1):
            todo_p = os.path.abspath(os.path.join(d, f"todo_{i:02d}.json"))
            done_p = todo_p.replace("todo_", "done_")
            dump({"lang": lang, "language": name, "script": script,
                  "instructions": rules, "write_to": done_p, "items": items}, todo_p)
            jobs.append((lang, todo_p, done_p))
        print(f"{lang} {name:<12} ingested {g} (rejected {b}); memory {len(tm)}; "
              f"to send {len(todo)} strings / {words} words -> {len(chunks)} chunks")
    if jobs:
        print("\nOne agent per chunk. Prompt:\n")
        print("  Read <todo>. Follow the instructions inside it. Write the translated file to\n"
              "  <done> in ONE Write call. Reply with one line: how many items you wrote.\n")
        for lang, t, d in jobs:
            print(f"  {t}  ->  {os.path.basename(d)}")
    else:
        print("\nNothing to send: every string is already in the memory.")


def cmd_apply(a):
    src, keys = load(a.src), parse_keys(a.keys)
    for lang in a.langs.split(","):
        lang_info(lang)
        g, b = ingest(a.work, a.tm, lang)
        tm = tm_load(a.tm, lang)
        out = json.loads(json.dumps(src))
        hit = miss = 0
        for path, _, text in walk(src, keys):
            e = tm.get(h(text))
            if e:
                set_path(out, path, e["t"])
                hit += 1
            else:
                # Left in English, in both modes, so lists keep their length
                # and order. `status` and this report say what is missing.
                miss += 1
        if a.overlay:
            out = prune(out, keys)
        path = a.out.replace("{lang}", lang)
        dump(out, path)
        pct = 100.0 * hit / max(1, hit + miss)
        print(f"{lang}: ingested {g} (rejected {b}); {hit} translated, {miss} still English "
              f"({pct:.1f}% done) -> {path}")


def prune(node, keys, key=None):
    """Overlay mode: keep ids and the text fields; drop everything else."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "id":
                out[k] = v
                continue
            p = prune(v, keys, k)
            if p not in (None, "", {}, []):
                out[k] = p
        return out
    if isinstance(node, list):
        # Every item is kept, even an empty one, because the app may match
        # list items by position.
        return [prune(v, keys, key) for v in node] if node else None
    if isinstance(node, str) and ("*" in keys or key in keys):
        return node
    return None


def cmd_status(a):
    src, keys = load(a.src), parse_keys(a.keys)
    uniq = {h(t): t for _, _, t in walk(src, keys)}
    for lang in a.langs.split(","):
        tm = tm_load(a.tm, lang)
        have = sum(1 for k in uniq if k in tm)
        print(f"{lang:<4} {have:>6}/{len(uniq)} unique strings in memory ({100.0*have/max(1,len(uniq)):.1f}%)")


def cmd_terms(a):
    """Export short, frequently used strings as a reusable starter memory."""
    src, keys = load(a.src), parse_keys(a.keys)
    only = parse_keys(a.only_keys) if a.only_keys else None
    # Strings with digits are project data (phone numbers, years, sample
    # values), not reusable terms.
    count = collections.Counter(t.strip() for _, k, t in walk(src, keys)
                                if (only is None or k in only) and not re.search(r"\d", t))
    common = [t for t, n in count.items() if n >= a.min_count and len(t.split()) <= a.max_words]
    for lang in a.langs.split(","):
        tm = tm_load(a.tm, lang)
        terms = {t: tm[h(t)]["t"] for t in sorted(common, key=str.lower) if h(t) in tm}
        existing = os.path.join(a.out, f"{lang}.json")
        if os.path.exists(existing):
            merged = load(existing)
            merged.update(terms)
            terms = dict(sorted(merged.items(), key=lambda kv: kv[0].lower()))
        dump(terms, existing)
        print(f"{lang}: {len(terms)} terms -> {existing}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan"); s.add_argument("--src", required=True); s.set_defaults(f=cmd_scan)

    s = sub.add_parser("seed")
    s.add_argument("--lang", required=True); s.add_argument("--tm", required=True)
    s.add_argument("--src"); s.add_argument("--keys"); s.add_argument("--translated")
    s.add_argument("--terms"); s.set_defaults(f=cmd_seed)

    for name, f in (("extract", cmd_extract), ("apply", cmd_apply), ("status", cmd_status), ("terms", cmd_terms)):
        s = sub.add_parser(name)
        s.add_argument("--src", required=True); s.add_argument("--keys", required=True)
        s.add_argument("--langs", required=True); s.add_argument("--tm", required=True)
        if name in ("extract", "apply"):
            s.add_argument("--work", required=True)
        if name == "extract":
            s.add_argument("--words", type=int, default=0, help="words per chunk (default: per language)")
        if name == "apply":
            s.add_argument("--out", required=True, help="output path, {lang} is replaced")
            s.add_argument("--overlay", action="store_true", help="write ids + translated text only")
        if name == "terms":
            s.add_argument("--out", required=True)
            s.add_argument("--min-count", type=int, default=3)
            s.add_argument("--max-words", type=int, default=8)
            s.add_argument("--only-keys", help="export only strings from these keys, e.g. label,documents")
        s.set_defaults(f=f)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
