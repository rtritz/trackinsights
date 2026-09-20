"""
Fetch the sectional and regional host names from IHSAA and save them as JSON.

Track.db records a tournament meet as "IHSAA Sectional 12"; the host school is
what people recognise. IHSAA publishes the pairing on its tournament pages, so
this job scrapes it once and writes the result to

    web/app/static/data/tournament_hosts/tournament_hosts.json

which common/tournament_hosts.py then reads. This is the ONLY code in the project
that talks to the network, and it is deliberately here in jobs/ rather than in
the request path -- see common/tournament_hosts.py for what that cost when it was
the other way round.

Run it when a new season's tournament assignments are published. From web/:

    python -m app.jobs.precompute_tournament_hosts
    python -m app.jobs.precompute_tournament_hosts --year 2027

Being scraped, it is best effort. A round that cannot be fetched -- the page has
moved, the site is down, the season is not published yet -- leaves whatever was
already in the file rather than blanking it, and says so. The site falls back to
the host recorded in Track.db regardless, so a failure here is cosmetic.
"""
import argparse
import html as html_lib
import re
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


from common.const import CONST  # noqa: E402
from common.tournament_hosts import (  # noqa: E402
    ALL_ROUNDS,
    ROUND_REGIONAL,
    ROUND_SECTIONAL,
    load_all,
    save_all,
    storage_key,
)

# The seasons worth keeping current. Older ones already have their hosts in the
# file and in Track.db; there is nothing to re-fetch.
DEFAULT_YEARS = [2026]

FETCH_TIMEOUT_SECONDS = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Sectional numbers run 1-32, regionals 1-8. Anything outside that is a misparse.
MAX_MEET_NUMBER = {ROUND_SECTIONAL: 32, ROUND_REGIONAL: 8}

# Both rounds are listed on the same kind of page, and both kinds of row link to
# MileSplit results. What separates them is a marker in the row's own text: a
# sectional row lists the schools in it, a regional row names the sectionals that
# feed it. Matching on that is what keeps one round's rows out of the other's.
ROW_MARKER = {ROUND_SECTIONAL: "schools:", ROUND_REGIONAL: "sectional host:"}


def _tournament_url(year, gender, round_name):
    gender_slug = "boys" if str(gender).strip().lower() == "boys" else "girls"
    season_slug = "%d-%02d" % (year - 1, year % 100)
    return ("https://www.ihsaa.org/sports/%s/track-field/%s-tournament?round=%ss"
            % (gender_slug, season_slug, round_name))


def _fetch(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_hosts(page_html, round_name):
    """Pull {meet number: host} out of an IHSAA tournament page.

    Split out from the fetch so it can be exercised against saved HTML without a
    network round trip -- which is the only way this parser can be tested at all,
    since the page it targets changes without notice.
    """
    marker = ROW_MARKER[round_name]
    limit = MAX_MEET_NUMBER[round_name]

    hosts = {}
    for block in re.findall(r"<p[^>]*>.*?</p>", page_html, flags=re.IGNORECASE | re.DOTALL):
        lower_block = block.lower()
        if "in.milesplit.com" not in lower_block or "/results" not in lower_block:
            continue
        if marker not in lower_block:
            continue

        text = re.sub(r"<[^>]+>", " ", block)
        text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()

        before_tickets = text.split("Tickets", 1)[0].strip()
        match = re.match(r"^(\d{1,2})\.\s*(.+)$", before_tickets)
        if not match:
            continue

        meet_num = int(match.group(1))
        host = re.sub(
            r"\s+\d{1,2}(?::\d{2})?\s*[ap]m(?:\s*[A-Z]{2})?$",
            "",
            match.group(2).strip(),
            flags=re.IGNORECASE,
        ).strip(" -")
        host = re.sub(r"\s*\(\d+\)\s*$", "", host).strip()

        if 1 <= meet_num <= limit and host and meet_num not in hosts:
            hosts[meet_num] = host

    return hosts


def fetch_hosts(year, gender, round_name):
    """Hosts for one season/gender/round, or None if the page could not be read."""
    url = _tournament_url(year, gender, round_name)
    try:
        page_html = _fetch(url)
    except (URLError, OSError, ValueError) as exc:
        print("  %s %s %s: could not fetch (%s)" % (year, gender, round_name, exc))
        return None
    hosts = parse_hosts(page_html, round_name)
    if not hosts:
        print("  %s %s %s: fetched, but nothing found -- the page layout may have changed"
              % (year, gender, round_name))
        return None
    return hosts


def main(years=None):
    years = years or DEFAULT_YEARS
    # Start from what is already saved so a round that fails to fetch keeps the
    # hosts it had, instead of being blanked by a bad afternoon at ihsaa.org.
    mapping = {key: dict(value) for key, value in load_all().items()}

    fetched, failed = 0, []
    for year in years:
        for gender in CONST.GENDER.ALL:
            for round_name in ALL_ROUNDS:
                print("Fetching %s hosts for %s %s..." % (round_name, year, gender))
                hosts = fetch_hosts(year, gender, round_name)
                if hosts is None:
                    failed.append("%s %s %s" % (year, gender, round_name))
                    continue
                mapping[storage_key(year, gender, round_name)] = hosts
                fetched += 1
                print("  %d meets" % len(hosts))

    path = save_all(mapping)
    print("Saved: %s  (%d fetched, %d kept from the previous build)"
          % (path, fetched, len(failed)))
    if failed:
        print("Could not fetch: %s" % ", ".join(failed))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, action='append', dest='years',
                        help='season to fetch; repeatable. Defaults to %s' % DEFAULT_YEARS)
    args = parser.parse_args()
    sys.exit(main(args.years))
