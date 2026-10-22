#!/usr/bin/env python3
"""Publish this month's scheme data for the app to download.

    python3 backend/publish.py           # build backend/publish/ and stamp the version
    python3 backend/publish.py --push    # also upload it (backend/config.json says where)

Before publishing it refuses when:
  - Data/merge_schemes.py finds an invalid record,
  - any of the 12 translations is missing text (the app would show English
    in the middle of, say, Tamil),
  - the catalogue shrank by more than a tenth since the last publish. That
    almost always means a broken batch file, not twenty schemes ending.

The upload goes to backend/publish/, laid out as the app expects:
    manifest.json
    data/schemes_en.json, data/schemes_gu.json, ...
It also writes Resources/data/version.json, so the next app build bundles
this same data and does not download it again.
"""
import argparse, datetime, glob, hashlib, json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACK = os.path.join(ROOT, "backend")
DATA = os.path.join(ROOT, "Resources", "data")
OUT = os.path.join(BACK, "publish")
LANGS = ["gu", "hi", "mr", "bn", "ta", "te", "kn", "ml", "pa", "or", "as", "ur"]
KEYS = ("title,department,brief,benefit,portalName,submitAt,helpline,lastVerified,"
        "eligibility,documents,demoSteps,label,value,hint")
SCHEMA = 1  # must match RemoteData::kSchemaVersion in the app


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(obj, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def fail(msg):
    print("NOT PUBLISHED:", msg)
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="upload after building")
    ap.add_argument("--min-coverage", type=float, default=100.0,
                    help="lowest translation coverage per language, in percent, that may be "
                         "published; anything missing shows in English")
    a = ap.parse_args()
    cfg = load(os.path.join(BACK, "config.json"), {})
    global OUT
    if cfg.get("publishDir"):
        # In the GitHub repository the app's files live at the repository
        # root, which is where GitHub Pages serves from.
        OUT = os.path.normpath(os.path.join(ROOT, cfg["publishDir"]))

    r = subprocess.run([sys.executable, os.path.join(ROOT, "Data", "merge_schemes.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return fail("merge_schemes.py reported errors:\n" + r.stdout[-2000:])

    r = subprocess.run([sys.executable, os.path.join(BACK, "itr", "scripts", "itr.py"), "status",
                        "--src", os.path.join(DATA, "schemes_en.json"), "--keys", KEYS,
                        "--langs", ",".join(LANGS), "--tm", os.path.join(BACK, "tm")],
                       capture_output=True, text=True)
    incomplete = []
    for l in r.stdout.splitlines():
        if "%" not in l:
            continue
        pct = float(l.rsplit("(", 1)[1].split("%")[0])
        if pct < a.min_coverage:
            incomplete.append(l)
    if incomplete:
        return fail("translations are incomplete:\n" + "\n".join(incomplete))

    en = load(os.path.join(DATA, "schemes_en.json"))["schemes"]
    last = load(os.path.join(OUT, "manifest.json"), {})
    last_n = last.get("files", {}).get("schemes_en.json", {}).get("schemes", 0)
    if last_n and len(en) < 0.9 * last_n:
        return fail(f"the catalogue shrank from {last_n} to {len(en)} schemes")

    # UTC, so the Mac and GitHub's servers agree, and always above the last
    # published version, so an app never sees a newer file as older.
    version = int(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M"))
    bundled = load(os.path.join(DATA, "version.json"), {}).get("dataVersion", 0)
    version = max(version, last.get("dataVersion", 0) + 1, bundled + 1)
    files = {}
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    for name in ["schemes_en.json"] + [f"schemes_{l}.json" for l in LANGS]:
        src = os.path.join(DATA, name)
        raw = open(src, "rb").read()
        n = len(json.loads(raw)["schemes"])
        shutil.copyfile(src, os.path.join(OUT, "data", name))
        files[name] = {"md5": hashlib.md5(raw).hexdigest(), "size": len(raw), "schemes": n}

    manifest = {"schemaVersion": SCHEMA, "minSchemaVersion": SCHEMA, "dataVersion": version,
                "published": datetime.datetime.now().isoformat(timespec="minutes"), "files": files}
    write_json(manifest, os.path.join(OUT, "manifest.json"))
    write_json({"dataVersion": version, "updateUrl": cfg.get("updateUrl", "")},
               os.path.join(DATA, "version.json"))
    print(f"built data version {version}: {len(en)} schemes, {len(files)} files -> {OUT}")

    if a.push:
        return push(cfg, version)
    return 0


def push(cfg, version):
    up = cfg.get("upload", {})
    kind = up.get("type", "none")
    if kind == "git":
        # A separate clone of the public data repository. publish/ is copied
        # into it, committed and pushed.
        repo = os.path.expanduser(up["dir"])
        dest = os.path.join(repo, up.get("subdir", ""))
        os.makedirs(os.path.join(dest, "data"), exist_ok=True)
        for p in glob.glob(os.path.join(OUT, "data", "*.json")):
            shutil.copy(p, os.path.join(dest, "data"))
        shutil.copy(os.path.join(OUT, "manifest.json"), dest)
        for cmd in (["git", "add", "-A"],
                    ["git", "commit", "-m", f"Scheme data {version}"],
                    ["git", "push", "-u", "origin", "HEAD"]):
            r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
            print("$", " ".join(cmd), "\n", (r.stdout + r.stderr).strip()[-800:])
            if r.returncode != 0 and cmd[1] != "commit":
                return fail(f"'{' '.join(cmd)}' failed")
        return 0
    if kind == "command":
        r = subprocess.run(up["command"], shell=True, cwd=OUT)
        return r.returncode
    print("upload.type is 'none' in backend/config.json; the files are ready in backend/publish/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
