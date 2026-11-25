"""Update the statewide program and event leaderboards (the school page's rank
popups) in dashboard_cache.db for selected seasons.

Run from web/: python -m app.jobs.precompute_rankings [2026 or 2023-2026]
Without an argument the job asks for a season or inclusive season range.
build_all runs rebuild_all(), which also stamps the cache as current.
"""
import argparse
import re
import sqlite3

from app import create_app, queries
from common import cache_db
from common.const import CONST


ROMAN_SUFFIX = re.compile(r'^(?:II|III|IV|VI{0,3}|IX|XI{0,3})$')
GEN_SUFFIX = re.compile(r'^(JR|SR)(\.?)$')


def _person_name(value):
    """Athlete names are stored shouting; print them as names.

    The rules come from looking at real data: roman-numeral
    suffixes stay capitalised, "Mc" takes a capital after it but "Mac" does not
    (MACIAS and MACKENZIE are ordinary names), and an apostrophe capitalises the
    next letter only when a single letter precedes it -- O'Brien does, Ahli'yla
    does not.
    """
    if not value:
        return ''
    words = []
    for word in str(value).split(' '):
        if not word:
            words.append(word)
            continue
        bare = word.upper()
        if ROMAN_SUFFIX.match(bare):
            words.append(bare)
            continue
        gen = GEN_SUFFIX.match(bare)
        if gen:
            words.append(gen.group(1)[0] + gen.group(1)[1].lower() + gen.group(2))
            continue
        parts = []
        for part in word.split('-'):
            lower = part.lower()
            if not lower:
                parts.append(part)
                continue
            out = re.sub(r'[a-z]', lambda m: m.group(0).upper(), lower, count=1)
            out = re.sub(r'^(\W*)Mc([a-z])',
                         lambda m: m.group(1) + 'Mc' + m.group(2).upper(), out)
            out = re.sub(r"^(\W*[A-Za-z])'([a-z])",
                         lambda m: m.group(1) + "'" + m.group(2).upper(), out)
            parts.append(out)
        words.append('-'.join(parts))
    return ' '.join(words)


def build_rankings(gender, season):
    """Every ranked list for one gender/season, as (event, payload) pairs.

    Trimmed to what the rank popup prints: the underlying rows carry meet ids,
    event types and lineups that no reader sees.
    """
    from sqlalchemy.orm import joinedload

    from app.models import School
    from app.queries.program_rankings import _build_statewide_program_rankings
    from app.queries.outlook import _grades_for_season
    from app.queries.scorecard import _event_ranked_rows, _relay_ranked_rows
    from app.queries.shared import _resolve_school_enrollment_for_year

    if str(season) == 'all-time':
        return []
    year = int(season)
    out = []

    # Enrollment for every school, resolved once. The popup filters on it, and
    # looking it up per row would be 394 lookups for the program table alone.
    enrollments = {}
    for school in School.query.options(joinedload(School.enrollments)).all():
        meta = _resolve_school_enrollment_for_year(school, year)
        enrollments[school.school_id] = meta.get('value')

    # Class year that season (FR/SO/JR/SR), for the popup's grade filter.
    grades = _grades_for_season(gender, year)

    table = _build_statewide_program_rankings(gender, year)
    out.append(('', {
        'kind': 'program',
        'title': 'Statewide Program Rankings',
        'subtitle': '%s %s \u2014 %d ranked programs' % (
            gender, year, len(table['leaderboard'])),
        'columns': ['Rank', 'School', 'Composite', 'Enrollment'],
        'rows': [
            {
                'rank': row['rank'],
                'school_id': row['school_id'],
                'name': row['school_name'],
                'value': round(row['composite_score'], 1)
                if isinstance(row.get('composite_score'), (int, float)) else None,
                'enrollment': enrollments.get(row['school_id']),
            }
            for row in table['leaderboard']
        ],
    }))

    for source, is_relay in ((_event_ranked_rows, False),
                             (_relay_ranked_rows, True)):
        for event, rows in (source(gender, year) or {}).items():
            out.append((event, {
                'kind': 'event',
                'title': event,
                'subtitle': '%s %s \u2014 %d %s ranked' % (
                    gender, year, len(rows), 'relays' if is_relay else 'athletes'),
                'columns': ['Rank', 'Relay' if is_relay else 'Athlete', 'School',
                            'Mark', 'Enrollment'],
                'rows': [
                    {
                        'rank': row.get('rank'),
                        'athlete_id': None if is_relay else row.get('athlete_id'),
                        'name': 'Relay' if is_relay else _person_name(row.get('athlete_name')),
                        'grade': None if is_relay else grades.get(row.get('athlete_id')),
                        'school_id': row.get('school_id'),
                        'school': row.get('school_name'),
                        'mark': row.get('result'),
                        'enrollment': enrollments.get(row.get('school_id')),
                    }
                    for row in rows
                ],
            }))
    return out


def parse_seasons(value):
    """Parse a four-digit year or an inclusive range of four-digit years."""
    match = re.fullmatch(r'\s*(\d{4})(?:\s*-\s*(\d{4}))?\s*', value)
    if not match:
        raise ValueError('Enter a season like 2026 or a range like 2023-2026.')
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first > last:
        raise ValueError('The first season must not be later than the last.')
    return list(range(first, last + 1))


def update_rankings(seasons, stamp=False):
    """Build both types for each gender and replace only those seasons.

    stamp=True also records the cache as built from the current Track.db (the
    fingerprint `build_all --check` and the deploy script compare). Only a
    rebuild of every season may stamp; a partial update leaves the stamp alone.

    Build everything before opening a write transaction, so an error cannot
    leave one gender, season, or ranking type only partially updated.
    """
    seasons = sorted(set(seasons))
    if not seasons:
        raise ValueError('Choose at least one season.')
    available = set(queries._covered_rank_seasons())
    missing = [year for year in seasons if year not in available]
    if missing:
        raise ValueError('No covered postseason data for: %s' %
                         ', '.join(map(str, missing)))

    rows = []
    for year in seasons:
        for gender in CONST.GENDER.ALL:
            rankings = build_rankings(gender, str(year))
            if not any(event == '' for event, _ in rankings):
                raise RuntimeError('Program leaderboard missing for %s %s.' % (gender, year))
            rows.extend((gender, str(year), event, cache_db.encode(payload))
                        for event, payload in rankings)
            print('  %s %s: %d ranked lists' % (gender, year, len(rankings)))

    conn = cache_db.connect(readonly=False)
    try:
        with conn:
            conn.executemany('DELETE FROM rankings WHERE gender=? AND season=?',
                             [(gender, str(year)) for year in seasons
                              for gender in CONST.GENDER.ALL])
            conn.executemany(
                'INSERT INTO rankings (gender, season, event, payload) VALUES (?, ?, ?, ?)',
                rows,
            )
            if stamp:
                cache_db.stamp(conn)
    finally:
        conn.close()
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='?', help='Season or inclusive range, e.g. 2026 or 2023-2026')
    args = parser.parse_args(argv)
    try:
        value = args.seasons if args.seasons is not None else input('Season or range (e.g. 2026 or 2023-2026): ')
        seasons = parse_seasons(value)
        app = create_app()
        with app.app_context():
            count = update_rankings(seasons)
    except (ValueError, RuntimeError, sqlite3.Error, EOFError) as exc:
        print('Rankings not updated: %s' % exc)
        return 1
    print('Updated %d program and event lists for %s.' %
          (count, ', '.join(map(str, seasons))))
    print('Other seasons were not rebuilt. Stored school pages may still show old')
    print('ranks until precompute_school_pages (or build_all) runs.')
    return 0


def rebuild_all(years=None):
    """build_all's step: the given seasons (default: every covered season), both
    genders, then stamp the cache as built from the current Track.db.

    Other seasons' lists are kept as they are.
    """
    app = create_app()
    with app.app_context():
        seasons = sorted(years) if years else sorted(queries._covered_rank_seasons())
        count = update_rankings(seasons, stamp=True)
    print('Updated %d program and event lists for %s.' % (count, ', '.join(map(str, seasons))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())