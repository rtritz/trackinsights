#!/bin/bash
# Deploy Track Insights to PythonAnywhere.
#
# The deployed layout is flatter than the repo: everything inside web/ is
# copied up, so ~/mysite holds app/, config.py, wsgi.py and data/ directly,
# with common/ beside them.
#
# Two artifacts arrive by two routes. Track.db is source data and travels in
# git. dashboard_cache.db is generated from it, weighs ~12MB and is rewritten
# whole on every build, so it is NOT in git -- it is published as a GitHub
# Release asset and downloaded below. Publishing an update is therefore:
#
#     cd web && python -m app.jobs.build_all
#     git add web/data/Track.db web/app/static/data && git commit && git push
#     gh release upload cache-latest web/data/dashboard_cache.db --clobber
#
set -euo pipefail

REPO=https://github.com/rtritz/trackinsights.git
TEMP=~/trackinsights-temp
SITE=~/mysite
WSGI=/var/www/www_trackinsights_org_wsgi.py
CACHE_URL=https://github.com/rtritz/trackinsights/releases/download/cache-latest/dashboard_cache.db

# Clones the default branch. To deploy a feature branch instead, add -b:
#   git clone --depth 1 -b update4 "$REPO" "$TEMP"

# ---- fetch first, so the live site is untouched until we have a good copy ----
# A network failure, a GitHub outage, or a leftover temp directory from an
# aborted run would otherwise leave ~/mysite wiped and the deploy half done.
rm -rf "$TEMP"
git clone --depth 1 "$REPO" "$TEMP"

# Is the clone what we think it is? Cheap, and it catches a wrong branch or a
# Track.db that never got committed before either can replace a working site.
test -f "$TEMP/web/wsgi.py"       || { echo "clone has no web/wsgi.py -- aborting"; exit 1; }
test -f "$TEMP/web/data/Track.db" || { echo "clone has no Track.db -- aborting";    exit 1; }

# ---- the dashboard cache, which is not in git ----
# Downloaded into the clone, so it is checked alongside everything else and a
# failure aborts while ~/mysite is still intact. -f makes curl exit non-zero on
# a 404 rather than writing GitHub's error page to disk as if it were a database.
echo "Downloading dashboard_cache.db from the release..."
curl -fsSL "$CACHE_URL" -o "$TEMP/web/data/dashboard_cache.db" \
  || { echo "could not download dashboard_cache.db -- aborting"; exit 1; }

# A truncated download, or an error page curl did accept, is still a file.
head -c 15 "$TEMP/web/data/dashboard_cache.db" | grep -q "SQLite format" \
  || { echo "downloaded cache is not a SQLite database -- aborting"; exit 1; }

# ---- is the precomputed data in step with the results database? ----
# Run against the CLONE, before ~/mysite is touched, so a stale build aborts a
# deploy that has not started instead of being reported by a site already
# serving it.
#
# PYTHONPATH="$TEMP" because common/ is a sibling of web/ in the repo and is not
# pip-installed on this server -- it only lands beside wsgi.py after the copy
# below. Without it the check dies on `import common` and reports that as a
# failed check.
#
# --check returns 0 current, 1 stale, 2 never built; anything else means the
# check itself failed. Each artifact is compared against its own season, so
# loading a new season flags that season's files and leaves older ones alone.
set +e
( cd "$TEMP/web" && PYTHONPATH="$TEMP" python -m app.jobs.build_all --check )
CHECK=$?
set -e
case $CHECK in
  0) echo "Precomputed data is current." ;;
  1) echo "ABORTING: precomputed data is STALE."
     echo "  Rebuild locally (cd web && python -m app.jobs.build_all), commit,"
     echo "  upload the cache to the release, then redeploy."
     echo "  To ship anyway -- a template fix while results are mid-rebuild --"
     echo "  add --warn-only to the check above for this run."
     exit 1 ;;
  2) echo "ABORTING: precomputed data was never built."
     echo "  The cache downloaded but has no contents, or the JSON is unstamped."
     exit 1 ;;
  *) echo "ABORTING: the freshness check itself failed -- see the output above."
     exit 1 ;;
esac

# ---- replace the site ----
cd "$SITE"
# Removes dotfiles too, unlike `rm -rf ./*`. A stale .git left behind by an
# older deploy sat here invisibly and grew to 203MB. Safe because nothing in
# ~/mysite is hand-maintained -- SECRET_KEY comes from the environment. If you
# ever keep a .env here, switch back to `rm -rf ./*` and clean up by hand.
find . -mindepth 1 -delete

cp -r "$TEMP/web/." "$SITE/"
cp -r "$TEMP/common" "$SITE/"
rm -rf "$TEMP"

# The cache came from the clone along with everything else, so this is the last
# chance to notice it did not survive the copy.
test -f "$SITE/data/dashboard_cache.db" \
  || echo "WARNING: dashboard_cache.db is missing from the site -- dashboards will be empty."

# ---- reload ----
# Touching the WSGI file is what the dashboard's Reload button does. Kept
# non-fatal: by this point the deploy has succeeded, and failing here would
# make a good deploy look broken.
touch "$WSGI" \
  && echo "Deployment complete and web app reloaded." \
  || echo "Deployed, but the reload failed -- reload from the PythonAnywhere dashboard."
