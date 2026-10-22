# Monthly data updates

The app ships with its scheme data, but government schemes change: amounts go
up, deadlines move, portals change address. This folder keeps the data current
without a new app release.

```
1st of each month
  monthly_check.py --apply   checks every link and page, makes safe fixes,
        |                    writes reports/YYYY-MM.md
        v
  research                   someone (or the scheduled Claude task) reads the
        |                    report and updates the English records that changed
        v
  translation                only the changed sentences go to the translators
        |                    (translation memory in tm/)
        v
  publish.py --push          checks everything, uploads manifest.json + data/
        |
        v
  the app                    downloads the new files within a day
                             (Data/RemoteData.cpp), and falls back to the
                             bundled data on any failure
```

## Files

| Path | What it is |
|---|---|
| `monthly_check.py` | Link and page check, safe fixes, the report |
| `publish.py` | Validation, version stamp, upload |
| `config.json` | `updateUrl` (where the app downloads from) and `upload` (how to get files there) |
| `months.py` | Month names in 13 languages for the "link checked" date |
| `tm/<lang>.json` | Translation memory: every English sentence and its translation |
| `itr/` | Copy of the translation tool from the `indian-language-translation` skill |
| `state/links.json` | How many runs in a row each link has failed |
| `state/snapshots/` | Last month's text of each scheme's main page |
| `reports/` | One report per month, in Markdown and JSON |
| `publish/` | What gets uploaded |

## Running a month by hand

```bash
python3 backend/monthly_check.py           # look first: changes nothing
python3 backend/monthly_check.py --apply   # make the safe fixes
```

Then open `backend/reports/<month>.md`.

- **Fixes** were applied automatically, and each one cannot be wrong. A deep
  link that has been dead for two months falls back to the portal homepage.
  A dead form download is hidden. A permanent move within the same site is
  followed.
- **Needs research** lists schemes whose official page changed a lot, or
  whose links have been unreachable for three months. Open each link, compare
  it with the record in `Data/work/_part_*.json`, and edit the English record
  if the amount, eligibility, documents, steps or address changed. If a
  scheme has ended, remove its record.

After editing English records:

```bash
python3 Data/merge_schemes.py
```

## Translating changed text

Only sentences the memory has never seen are sent for translation, so a normal
month needs a handful of strings, not the whole catalogue.

```bash
I=backend/itr/scripts/itr.py
K=title,department,brief,benefit,portalName,submitAt,helpline,lastVerified,eligibility,documents,demoSteps,label,value,hint
L=gu,hi,mr,bn,ta,te,kn,ml,pa,or,as,ur
python3 $I extract --src Resources/data/schemes_en.json --keys $K --langs $L --tm backend/tm --work backend/work
```

`extract` lists the chunk files. Each chunk goes to one translator, a Claude
agent, with the prompt it prints: "Read <todo>. Follow the instructions inside
it. Write ... in ONE Write call." Then:

```bash
python3 $I apply --src Resources/data/schemes_en.json --keys $K --langs $L --tm backend/tm \
        --work backend/work --out 'Resources/data/schemes_{lang}.json' --overlay
```

`apply` checks every translated item. It rejects an item that changed a
number, a link or a placeholder, or that is in the wrong script, and the next
`extract` sends rejected items again.

## Publishing

```bash
python3 backend/publish.py          # build backend/publish/, stamp the version
python3 backend/publish.py --push   # and upload
```

It refuses to publish when a record is invalid, when any language is missing
text, or when the catalogue shrank by more than a tenth.

`publish.py` also writes `Resources/data/version.json`. The next app build
therefore bundles this data and does not download it a second time.

## Where the data is hosted

Set two things in `config.json`:

- `updateUrl`: the public HTTPS address of the folder that holds
  `manifest.json`, ending in `/`. Then run `publish.py` once, so
  `Resources/data/version.json` carries the same address, and rebuild the app.
  An app built while `updateUrl` was empty never checks for updates.
- `upload`: either
  `{"type": "git", "dir": "~/path/to/data-repo-clone"}` for a GitHub
  repository served by GitHub Pages or jsDelivr, or
  `{"type": "command", "command": "firebase deploy --only hosting"}`, which
  runs inside `backend/publish/`, or any other upload command.

The address must be HTTPS. Android blocks plain HTTP by default.

## Where it runs

On GitHub Actions, in the public repository GameTheory2016/sarkari-yojana-data
(`.github/workflows/monthly.yml`), at 10:00 India time on the 1st of each
month. The steps run inside `pipeline/`. It needs no Mac, no Claude plan and
no money.

- **AI step:** runs only if the repository has a `GEMINI_API_KEY` secret,
  a free key from aistudio.google.com.
- **Geo-blocking:** GitHub's servers are outside India, and about half of
  the state portals refuse them. Those links show as UNREACHABLE or BLOCKED,
  and nothing is changed because of them. Only real 404s, seen on two runs
  in a row (three for form downloads), lead to a fix.
- **The repository's copy is the live one.** Before building an app release,
  run `python3 backend/sync_repo.py --from`, so the app bundles current data.
  After editing scripts or English records here, run `--to`, then commit and
  push the clone.
