# Project Guide

You are joining a working web application with real users. This page is the
orientation: what the project is, how it is laid out, and where to go when you
want to change something.

Read this once before your first change. It is short on purpose.

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
  dashboard_cache.db        prepared answers, one row per school/season
  static/data/*.json        prepared answers for the prediction pages
      |
      |   a visitor opens a page
      v
  Flask route -> one lookup -> template -> HTML
```

Two consequences worth remembering:

- **After you change the data, you must rebuild.** Otherwise the site keeps
  showing the old answers. See §6.
- **Generated files are not edited by hand.** `dashboard_cache.db` and the JSON
  under `static/data/` are outputs. Editing them is pointless; the next rebuild
  overwrites your changes.

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
│           └── data/           GENERATED JSON. Do not edit.
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
python -m app.jobs.build_all        # ~10 minutes
```

Then commit the changed files under `web/data/` and `web/app/static/data/`.

To check whether a rebuild is needed:

```bash
python -m app.jobs.build_all --check
```

The dashboard notices this itself: it stores a fingerprint of the database it
was built from, and shows a warning banner on the page when they no longer
match. You do not have to remember — but the banner is visible to visitors, so
do not leave it showing.

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

`school-dashboard-v4.css` is ordinary hand-written CSS and is safe to edit.

### JavaScript lives in its own file

Each page's JavaScript is in `static/js/`, named after the template it belongs
to: `school-dashboard.html` -> `js/school-dashboard.js`. Do not put JavaScript
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
- **Do not hand-edit generated files**: `dashboard_cache.db`, anything under
  `static/data/`, or `output.css`.
- **Do not put secrets in the code.** `config.py` reads them from the
  environment; keep it that way.
- **There are two school dashboards.** `/school-dashboard/<id>` is the live one.
  `/school-dashboard-v4/<id>` is a prototype of a faster architecture. Both work;
  ask before changing which one is the default.

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

## 10. Deploying

The site runs on PythonAnywhere. Deploying replaces the app directory with a
fresh clone, because the deployed layout is flatter than the repo: everything
inside `web/` is copied up to the top, so `~/mysite/` holds `app/`, `config.py`,
`wsgi.py` and `data/` directly, with `common/` beside them.

```bash
cd ~/mysite
rm -rf ./*
git clone https://github.com/<user>/trackinsights.git ~/trackinsights-temp
cp -r ~/trackinsights-temp/web/. ~/mysite/
cp -r ~/trackinsights-temp/common ~/mysite/
rm -rf ~/trackinsights-temp
```

Then reload the web app from the PythonAnywhere dashboard.

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
