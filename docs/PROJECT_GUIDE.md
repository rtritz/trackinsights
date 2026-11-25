# Project Guide

You are joining a working web application with real users. This page is the
orientation: what the project is, how it is laid out, and where to go when you
want to change something.

Read this once before your first change. It is short on purpose.

Want it on paper? `python docs/make_pdf.py` writes `docs/PROJECT_GUIDE.pdf`.

---

## 1. What this is

Track Insights is a Flask website for Indiana high school track & field. It
reads a SQLite database of meet results (sectionals, regionals, state finals)
and turns them into dashboards, rankings and reports.

There is no user-generated content and nothing to log into. The site reads data,
analyses it, and renders pages.

---

## 2. The one idea that explains the layout

**Expensive work happens before anyone visits the site, not while they wait.**

Working out where a school ranks statewide means examining every result in the
state. Doing that on each page load took seconds. So it is done in advance, by
scripts you run yourself, and the results are stored. A page request then just
looks up an answer that already exists.

```
  Track.db                  the source data: every meet result
      |
      |   you run: python -m app.jobs.build_all
      v
  dashboard_cache.db        prepared answers: every school page, the statewide
                            rankings, and the data behind the report pages
      |
      |   a visitor opens a page
      v
  Flask route -> one lookup -> template -> HTML
```

Two consequences worth remembering:

- **After you change the data, you must rebuild.** Otherwise the site keeps
  showing the old answers. See §6.
- **Generated files are not edited by hand.** `dashboard_cache.db` is an
  output. Editing it is pointless; the next rebuild overwrites your changes.

---

## 3. Where everything lives

```
trackinsights/
├── common/                     Shared library. Imported by BOTH the website and
│                               the standalone programs. Database access, unit
│                               conversion, constants.
│
├── web/                        The website.
│   ├── wsgi.py                 Start here to run it. Also what the web server
│   │                           imports to serve the site.
│   ├── config.py               Settings. Reads secrets from the environment.
│   ├── data/
│   │   ├── Track.db            SOURCE DATA. The real results. Tracked in git.
│   │   └── dashboard_cache.db  GENERATED. Rebuilt by the jobs. Do not edit.
│   └── app/                    The application itself.
│       ├── __init__.py         Flask app factory: builds the app, registers
│       │                       blueprints and template filters.
│       ├── models.py           Database tables as Python classes.
│       ├── routes/             URL -> function. Thin: parse the request, fetch,
│       │                       render. No analysis here.
│       ├── queries/            Reading and analysing the database, by feature.
│       ├── services/           Preparing a whole page's data.
│       ├── analytics/          Standalone statistical engines.
│       ├── jobs/               The precompute scripts you run by hand.
│       ├── templates/          Jinja HTML. insights/ holds the insight pages.
│       └── static/
│           ├── css/            output.css is BUILT from input.css (see §7)
│           ├── js/
│           ├── images/
│           ├── reports/        Generated PDFs
│
│
│   templates/ and static/ live inside app/ because that is where Flask looks
│   for them with no configuration at all.
│
├── standalone/                 NOT part of the website. Scraping notebooks,
│                               one-off scripts, generated reports.
├── tests/
└── docs/
```

---

## 4. "Where do I go if I want to change…"

| I want to change | Go to |
|---|---|
| What a page looks like | `web/app/templates/` |
| Page styling | `web/app/static/css/` — but see §7 first |
| Page behaviour in the browser | `web/app/static/js/` — **one file per page, named after the template** |
| What URL shows what | `web/app/routes/` |
| How a number is calculated | `web/app/queries/` — pick the feature file |
| What data a whole page needs | `web/app/services/` |
| A database table | `web/app/models.py` |
| A prediction model | `web/app/analytics/` |
| How precomputed data is built | `web/app/jobs/` |
| Where precomputed data is stored | `common/cache_db.py` (the tables in `dashboard_cache.db`) |
| Something used by scripts too | `common/` |

### Inside `queries/`

This is where most analysis lives, split by feature so you do not have to read
all of it:

| File | Holds |
|---|---|
| `shared.py` | Helpers every feature uses. Start here if something is used everywhere. |
| `school_dashboard.py` | The school dashboard pages themselves |
| `rankings.py` | Where a program sits statewide (the expensive one) |
| `scorecard.py` | One school's entries, round by round |
| `outlook.py` | Returning athletes and head-to-head against last season |
| `athletes.py` | Athlete dashboards, result rankings, badges |
| `meets.py` | Meet results, team scoring, relays |
| `qualifiers.py` | Who advanced to regionals and state |
| `percentiles.py` | Percentile tables |
| `insights.py` | Sectional trends, hypothetical rankings |
| `search.py` | Site-wide search |

Everything is re-exported from the package, so `from app.queries import X`
works no matter which file `X` is in.

---

## 5. Running it

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[web,standalone,dev]"

cd web
python wsgi.py                    # http://localhost:5000
```

`wsgi.py` cannot be called `app.py`: `app/` beside it is the package, and Python
would not know which one `import app` meant. WSGI is the interface Python web
servers speak, and the deployed site imports `app` out of this same file -- so
it is the honest name for what it is.

Debug mode is on, so Python and template edits reload automatically. CSS and JS
changes need a hard refresh (Ctrl+Shift+R).

Run the tests before and after any change:

```bash
python -m pytest tests/ -q
```

They also run automatically on every push (see `.github/workflows/tests.yml`),
so a broken change is caught even if you forget.

Most of the suite is a **smoke test**: it walks every route Flask knows about and
checks each one answers, then crawls the rendered pages and checks every script
and stylesheet they reference actually exists. That is shallow on purpose -- it
does not check a page is *correct* -- but it catches the mistakes that moving
code around causes: a renamed template, a query function that no longer exists,
a `<script src>` pointing at the wrong filename. That last one is worth knowing
about: a missing script fails **silently**, with the page simply sitting there
doing nothing, so it is the kind of bug you can stare straight through.

If you add a route that takes a URL parameter, add a test value for it in
`tests/test_routes_smoke.py` -- the suite will tell you to.

---

## 6. After the data changes

If you add or correct meet results in `Track.db`, the prepared answers are now
out of date. Rebuild them:

```bash
cd web
python -m app.jobs.build_all        # current season, ~2-3 minutes
python -m app.jobs.build_all --all  # every season
```

Then commit `web/data/Track.db` and publish the cache (§10).

**The current season is the newest year with results in `Track.db`.** Nothing
to set: loading the first 2027 result (either gender) makes 2027 current. A
plain `build_all` builds, for both genders:

- the current season's school pages and statewide rankings, plus every
  school's All-Time page. Older seasons' pages are left alone: the parts of a
  page that cover every season (the season picker and bars, program records,
  returners) are read from the All-Time page, so they stay current;
- the qualifier pages' data (regional qualifiers, combined regional rankings
  and results, state qualifiers) for the current season only. Those pages show
  only the current season, so older seasons' data is removed.

A round no team of that gender has run yet shows as **Pending**, never as zero
-- e.g. boys pages between the girls' and boys' sectionals.

**During the postseason** results arrive six times (each gender's sectional,
regional and state). Each time:

1. Run the scraper notebook (`standalone/notebooks/MS Scrapper.ipynb`). Its
   last cell runs `build_all`, which also fetches the season's host names
   from ihsaa.org.
2. Check the results and a couple of pages on your local server.
3. Commit `web/data/Track.db` and push (the push hook publishes the cache).
4. Deploy.

To check whether a rebuild is needed:

```bash
python -m app.jobs.build_all --check
```

The dashboard notices this itself: it stores a fingerprint of the database it
was built from, and shows a warning banner on the page when they no longer
match. You do not have to remember — but the banner is visible to visitors, so
do not leave it showing.

### Updating statewide ranking lists for selected seasons

Program rankings and individual and relay event rankings are precomputed
together. From `web/`, run `python -m app.jobs.precompute_rankings` and enter a
year such as `2026` or an inclusive range such as `2023-2026` when prompted.
For automation, pass the same year or range as an argument, for example
`python -m app.jobs.precompute_rankings 2026`.

This replaces both boys' and girls' ranking lists only for the selected seasons;
other seasons' lists are preserved. It can initialize the ranking tables if the
cache does not yet exist. The update is transactional: a failed build or write
does not replace existing rankings.

**This is a rankings-only update.** Dashboard page payloads contain their own
rank values and other data, and are not refreshed by this job. They can still
show old numbers or be missing even when their leaderboard has been updated.
The dashboard's freshness stamp is deliberately not changed. Run the full
dashboard rebuild or `build_all` to refresh page payloads and other artifacts
(`--season YYYY` after correcting an older season). The cache is not in git;
publish the updated cache release asset as described in §10 when deploying.

---

## 7. A trap: CSS is built, not hand-written

`static/css/output.css` is **generated** by Tailwind from `input.css`. If you
edit `output.css` directly, the next build erases your work.

```bash
npm install
cd web
npx @tailwindcss/cli -i ./app/static/css/input.css \
                     -o ./app/static/css/output.css --minify
```

### JavaScript lives in its own file

Each page's JavaScript is in `static/js/`, named after the template it belongs
to: `school-page.html` -> `js/school-page.js`. Do not put JavaScript
back inside a `<script>` tag in a template -- it loses syntax checking, cannot be
cached by the browser, and hides the code from anyone reading the directory.

If the script needs a value from Python, put it on an element as a `data-`
attribute and read it from the DOM:

```html
<div id="dashboard-content" data-athlete-id="{{ athlete_id }}">
```
```js
const athleteId = Number(document.getElementById('dashboard-content').dataset.athleteId);
```

That is what lets the file live outside the template. Templating values directly
into JavaScript ties it to Jinja and it can never move.

**Name your CSS classes carefully.** daisyUI is compiled into `output.css`, and
it already uses `.modal`, `.tab`, `.tabs`, `.card`, `.badge`, `.toggle`,
`.alert` and `.dropdown`. Reusing one of those names means inheriting its styles
even inside your own scoped block — this has caused two real bugs. Check
`output.css` before inventing a class name.

---

## 8. Things to be careful with

- **`Track.db` is the real data.** It is tracked in git, so a bad write is
  recoverable — but check with whoever maintains the data before changing it.
- **Do not hand-edit generated files**: `dashboard_cache.db` or `output.css`.
- **Do not put secrets in the code.** `config.py` reads them from the
  environment; keep it that way.

---

## 9. Making a change safely

1. `python -m pytest tests/ -q` — confirm it passes *before* you start.
2. Make your change.
3. Run the app and look at the page you changed.
4. Run the tests again.
5. If you touched anything that reads the database, rebuild (§6).
6. Commit with a message describing *why*, not just what.

If you are unsure whether something is used, search for it before deleting:

```bash
grep -rn "the_name" --include=*.py --include=*.html --include=*.js .
```

A file with no Python import may still be run by hand, by a job, or by a
notebook. Absence of an import is not proof it is dead.

---

## 9a. Getting the cache

`dashboard_cache.db` is not in git -- it ships as a release asset (§10) -- so a
fresh clone or a newly pulled branch does not have it. Get the published one
with one command:

```bash
cd web
python -m app.jobs.get_cache
```

Run it after you clone, and again whenever the data has been republished
(someone tells you, or the rank popups look out of date). It is safe to re-run:
the download is checked before it replaces your copy, so a failed download
leaves the old one in place. It ends by saying whether the cache matches your
`Track.db`; if it does not (you pulled newer results than were published, or
edited `Track.db`), run `python -m app.jobs.build_all` instead.

**What needs the cache, and what does not:**

| Without the cache | With it |
|---|---|
| School pages work: in development they build themselves (debug mode, or `TI_LIVE_DASHBOARD=1`), so code and template changes show on refresh | Same -- development still builds school pages live |
| Rank popups are empty | Rank popups list the statewide rankings |
| Report pages say "not available yet"; qualifier lists are computed live (slow) | Report pages and qualifier lists load instantly |

So you do not need it to develop, run the tests, or change query or template
code. You do need it to try the rank popups or the report pages.

**Do not commit the cache.** It is ~36MB, rewritten on every rebuild and growing
each season; committed, every rebuild would add a full copy to everyone's clone
forever, and two branches that rebuilt it could not be merged. `.gitignore`
keeps it out.

The deployed site reads stored pages from the cache. It exists because this
analysis took seconds per page and PythonAnywhere measured 15-25x slower than a
development machine. A page missing from the cache is still built live there,
slowly, rather than failing.

---

## 10. Deploying

The site runs on PythonAnywhere. Deploying replaces the app directory with a
fresh clone, because the deployed layout is flatter than the repo: everything
inside `web/` is copied up to the top, so `~/mysite/` holds `app/`, `config.py`,
`wsgi.py` and `data/` directly, with `common/` beside them.

**Two files, two channels.** `Track.db` is source data and travels in git.
`dashboard_cache.db` is *generated* from it (`common/cache_db.py` describes its
tables), weighs ~36MB, and is rewritten on every rebuild -- tracking it would add
a fresh copy to history every time results were updated. It ships as a GitHub Release asset instead, which the
deploy downloads. Releases sit outside the git object graph, so replacing the
asset costs nothing in clone size.

So publishing an update is two steps, not one:

```bash
# 1. Rebuild, then commit the things that belong in git.
cd web && python -m app.jobs.build_all
cd .. && git add web/data/Track.db && git commit && git push

# 2. Publish the cache. Creates the release if it is missing, replaces the
#    asset if it is not, and refuses to publish a cache that does not match
#    the Track.db you just pushed.
./docs/publish.sh
```

Both run on your machine. The server only consumes: `docs/deploy.sh` clones the
repo and downloads that asset. Creating the release is not a step you have to
remember -- `publish.sh` does it the first time and skips it thereafter.

**Or let the push do it.** `docs/hooks/pre-push` runs `publish.sh` for you when
you push `main` and the cache has changed, which makes step 2 disappear:

```bash
git config core.hooksPath docs/hooks   # the data publisher only -- see below
```

**Only the person who publishes data should turn this on**, and only on their own
machine. That setting lives in `.git/config`, which is never committed, so
cloning does not enable it -- everyone else gets an inert file in `docs/hooks/`,
which is what you want: publishing needs the built cache and write access to the
repository's releases, so for a teammate it could only fail, and a failed publish
stops the push.

Then a data update is just rebuild, commit, push. The hook publishes nothing
when the cache has not moved, so ordinary pushes are unaffected.

It fires on **any** branch, not only `main`. Work here reaches `main` through a
pull request merged on GitHub, so `main` is never pushed from a machine -- a hook
that waited for one would never run. The cache belongs to a `Track.db` rather
than to a branch, and the branch you push is the one about to become `main`.

If publishing fails it stops the push, because pushing new results next to an
old cache is the state the whole arrangement exists to prevent. `git push
--no-verify` skips it deliberately.

The script lives at [`docs/deploy.sh`](deploy.sh) -- copy it into a Bash
console on PythonAnywhere and run it there. Keeping one copy rather than
two means the guide cannot drift from what you actually run.


Then reload the web app from the PythonAnywhere dashboard.

Three things in that script are there for a reason:

- **`--depth 1`.** A full clone pulls the whole history, which is mostly old
  binaries; the deploy only ever needs the tip.
- **The `case`, not `|| echo "stale"`.** `--check` returns 0 current, 1 stale,
  2 never built, and anything else means the check itself broke. Collapsing
  those into one message once reported a `ModuleNotFoundError` as stale data.
- **The module is `app.jobs.build_all`**, not `backend.jobs.build_all`. The
  deploy copies `web/`'s contents up, so the package sits at `~/mysite/app/`.
- **The cache is fetched before `~/mysite` is wiped.** Downloading after the
  wipe would leave the site with no dashboards if GitHub were unreachable; this
  way a failed download aborts a deploy that has not started.
- **`--check` runs against the clone and aborts.** It used to run after the
  copy and only print a warning, which meant you learned the data was stale
  from a site that was already serving it.

### What `--check` actually verifies

Every precomputed artifact records a fingerprint of the data it was built from,
and `--check` recomputes that fingerprint and compares. It is the one mechanism
that answers *did the results change without the precompute being re-run?*

**The report data is fingerprinted per season, not on the whole database.**
Each report (the cache's `artifacts` table) covers a single year and gender, so
its stamp covers only that season's meets, results, relays, the athletes and
schools appearing in them, and that year's enrollments. The row records the
scope alongside the hash.

That scoping is what makes the check usable during a postseason. A whole-file
hash of Track.db answers "did anything change?", which during two weeks of
loading results is *always yes* -- so every artifact of every past season reads
as stale at once, and the only thing anyone learns is to ignore the warning.
Scoped, you get the answer worth having:

| what you did | what gets flagged |
|---|---|
| Loaded 2027 sectional results | the 2027 reports. 2026 untouched. |
| Corrected a 2026 mark | the 2026 reports for that gender. 2027 untouched. |
| Renamed a school that ran in 2026 | the 2026 reports. |
| Added a 2027 athlete at a new school | nothing from 2026. |

So keeping old seasons' reports costs nothing in noise. They stay serveable, and
they only speak up when that season's data genuinely moves -- which is exactly
when you do want to rebuild them.

**The rankings and school pages are the exception, and deliberately so.** A
school page shows every season at once and its statewide ranking shifts when any
season shifts, so a new 2027 result really does make the 2026 view of it stale.
They keep a whole-file hash, which means *any* results change asks for a
rebuild. That is correct, not noise -- but it is the reason a deploy
mid-postseason will usually want `build_all` run first.

The tournament hosts are exempt entirely: they come from ihsaa.org, not from
Track.db.

### When you need to deploy anyway

`--check --warn-only` prints the same report and exits 0. For shipping a
template or styling fix while the results are mid-rebuild, where blocking the
deploy would be the wrong answer. It is a deliberate override -- the deploy
script above uses the gate.

**The server needs three packages and nothing else:**

```bash
pip install Flask Flask-SQLAlchemy pandas
```

No `pip install -e .` here -- `pyproject.toml` is at the repo root and the
deploy does not copy it, so there is no project for pip to install. `common/`
needs no install either: it lands beside `wsgi.py` in `~/mysite`, which is
already on `sys.path`.

Those three are the `[web]` extra plus the base dependency in
`pyproject.toml`; keep them in step by hand, or copy `pyproject.toml` across
in the deploy and use `pip install ".[web]"` instead.

Do **not** install the `standalone` or `dev` extras there. They pull jupyter,
matplotlib, Pillow and reportlab -- roughly 300 MB that never runs on the
site, and enough to crowd a 1 GB quota. Note that installing the lean set
does not remove them: pip never prunes, so an environment that already has
them has to be rebuilt to get the space back.

**The WSGI configuration file** (edited on PythonAnywhere, not in this repo)
needs one line pointing at the entry point:

```python
from wsgi import app as application
```

That file is *not* part of the repo, so renaming `wsgi.py` here would not
change it — the site would 500 on the next reload with no clue in the code as
to why. If you rename the entry point, change that line at the same time.

Two things about that flatter layout are worth knowing, because both have
already caused quiet bugs:

- **`common/const.py` works out where `data/` is by checking whether a `web/`
  directory exists.** In the repo it does; on the server it does not. Hard-code
  `<root>/web` and every precomputed file silently fails to load while the site
  keeps serving pages normally.
- **Build the precomputed data locally and commit it**, then deploy. A fresh
  clone has whatever is in git; it does not run the jobs. If you deploy without
  rebuilding, the dashboards show a stale-data banner.
