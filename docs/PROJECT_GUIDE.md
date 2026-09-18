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
      |   you run: python -m backend.jobs.build_all
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
│   ├── app.py                  Start here to run it.
│   ├── config.py               Settings. Reads secrets from the environment.
│   └── backend/
│       ├── __init__.py         Flask app factory: builds the app, registers
│       │                       blueprints and template filters.
│       ├── models.py           Database tables as Python classes.
│       ├── routes/             URL -> function. Thin: parse the request, fetch,
│       │                       render. No analysis here.
│       ├── queries/            Reading and analysing the database, by feature.
│       ├── services/           Preparing a whole page's data.
│       ├── analytics/          Standalone statistical engines.
│       └── jobs/               The precompute scripts you run by hand.
│   ├── data/
│   │   ├── Track.db            SOURCE DATA. The real results. Tracked in git.
│   │   └── dashboard_cache.db  GENERATED. Rebuilt by the jobs. Do not edit.
│   └── frontend/
│       ├── templates/          Jinja HTML. insights/ holds the insight pages.
│       └── static/
│           ├── css/            output.css is BUILT from input.css (see §7)
│           ├── js/
│           ├── images/
│           ├── reports/        Generated PDFs
│           └── data/           GENERATED JSON. Do not edit.
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
| What a page looks like | `web/frontend/templates/` |
| Page styling | `web/frontend/static/css/` — but see §7 first |
| Page behaviour in the browser | `web/frontend/static/js/` |
| What URL shows what | `web/backend/routes/` |
| How a number is calculated | `web/backend/queries/` — pick the feature file |
| What data a whole page needs | `web/backend/services/` |
| A database table | `web/backend/models.py` |
| A prediction model | `web/backend/analytics/` |
| How precomputed data is built | `web/backend/jobs/` |
| Something used by scripts too | `common/` |

### Inside `queries/`

This is where most analysis lives, split by feature so you do not have to read
all of it:

| File | Holds |
|---|---|
| `shared.py` | Helpers every feature uses. Start here if something is used everywhere. |
| `school_dashboard.py` | School dashboards and the statewide program rankings |
| `athletes.py` | Athlete dashboards, result rankings, badges |
| `meets.py` | Meet results, team scoring, relays |
| `qualifiers.py` | Who advanced to regionals and state |
| `percentiles.py` | Percentile tables |
| `insights.py` | Sectional trends, hypothetical rankings |
| `search.py` | Site-wide search |

Everything is re-exported from the package, so `from backend.queries import X`
works no matter which file `X` is in.

---

## 5. Running it

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[web,standalone,dev]"

cd web
python app.py                     # http://localhost:5000
```

Debug mode is on, so Python and template edits reload automatically. CSS and JS
changes need a hard refresh (Ctrl+Shift+R).

Run the tests before and after any change:

```bash
python -m pytest tests/ -q
```

---

## 6. After the data changes

If you add or correct meet results in `Track.db`, the prepared answers are now
out of date. Rebuild them:

```bash
cd web
python -m backend.jobs.build_all        # ~10 minutes
```

Then commit the changed files under `web/data/` and `web/frontend/static/data/`.

To check whether a rebuild is needed:

```bash
python -m backend.jobs.build_all --check
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
npx @tailwindcss/cli -i ./frontend/static/css/input.css \
                     -o ./frontend/static/css/output.css --minify
```

`school-dashboard-v4.css` is ordinary hand-written CSS and is safe to edit.

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
