"""Read-only school dashboard payload contract.

All data covers postseason meets from MIN_RECORDS_YEAR. A result unit is an
athlete/event/year or relay/event/year, including no-marks. Top-level keys:

* school: id, name, city, school_type, logo_url, enrollment and its source year
    and exactness; gender and season are the normalized selected filters; years is
    every covered year across both genders, newest first, so gender changes keep
    the selected season; latest_year is the newest
    year in which the school participated; is_all_time identifies the selection.
* summary: result_units, athletes, sectional_placers, regional_entries,
    regional_placers, state_entries, state_placers, sectional_champions,
    sectional_team (rank, total_teams, points, meet_id or None), program rank,
    ranked_schools, rank_cache_missing, qualifier_details (Regional/State lists),
    sentence and top_performers. All-time counts sum season units; team and program
    ranks are None. Qualifiers are observed participants, not inferred scratches.
* performances: every valid season/event best; rank, rank_total and percentile
    refer to that season's cached event leaderboard. stage is the mark's stage;
    final_stage, place and prelim describe the furthest observed round. Top
    performers deduplicate individuals across events/years and relays by event,
    retain top-half annual percentiles in all-time, and prioritize state placers/qualifiers.
* events: one per gender-appropriate event with name, label, group, unit,
    lower_is_better, entries, cached distribution (marks, count, missing_years,
    skipped_rows, complete), and regional_cutoff/state_cutoff lists. Cutoffs
    are observed advancing places; state additionally considers that year's
    published standard. Missing mappings/marks do not imply a cutoff.
* results: stages and rows from the per-year scorecard, including placeholders;
    rows retain stages, final_stage, gap, cutoff_value, gap_value and cached rank
    and rank_total. All valid gaps remain visible; only gaps within 3% are highlighted.
* outlook: latest school season roster, returning/graduating/unknown counts and
    regional_returners, state_returners, regional_graduating, state_graduating
    lists of named individuals with their events; relay legs are not inferred.
* history: every covered year with the summary counts, sectional team and
    cached program rank, even if the school did not participate. bests: every
    event with a possibly empty entries list of tied all-time bests.
* data: program_missing_years, event_cache_issues, unmatched_entries and a
    complete flag. Missing, malformed or mismatched cache rows make ranks
    unavailable, never a request-time ranking fallback.

Result gaps measure qualifying only -- how far a Sectional mark was from the
Regional cut, or a Regional mark from the State cut -- using the same
meet-specific cutoffs as the charts. Marks at State get no gap. Attendance and grades come from source rows. Unknown
values are None, not zero unless a count is genuinely empty.

Nested shapes and rules:

* A performance has event, athlete_id (None for a relay), name, is_relay,
    year, grade, mark, value, meet_id, stage, stages (ordered stage names),
    final_stage, place, prelim, rank, rank_total and percentile. The percentile
    is 1 - (rank - 1) / rank_total, from the annual cached competition rank and
    the original leaderboard length, including tied or malformed rows. An
    unverified cache match has all three rank fields None. Dedupe selects each
    individual's highest percentile or each relay event's highest percentile;
    ties use the same presentation order. The presentation order is state final
    top-nine placers, other state participants, then others, each sorted by
    descending percentile, ascending furthest place, name, event and newer year.
* A distribution mark has value, mark, rank, name, athlete_id, school_id and
    year; all-time combines each athlete's or school's best mark and clears its
    rank. totals maps each cached year to its original number of leaderboard rows.
    A cutoff has value, mark, meet_id, place and path ('observed' or 'standard');
    the standard has no place. Regional means sectional-to-regional and state
    means regional-to-state. Only the regional at the actual or mapped meet is
    used. Standards are never silently substituted from another year.
* Each result row is the shared season scorecard row plus year and gap alias.
    It includes event, group when supplied, entry_type (individual/relay/none),
    athlete_id, name, grade, stages (stage -> mark_display, result_value,
    has_mark, place, round), best_stage, mark_display, result_value, rank,
    rank_total, final_stage, cutoff_display, cutoff_path, cutoff_value,
    gap_display, gap_value, gap, qualified_did_not_compete and tied_cutoff where
    available. Placeholder rows retain the shared scorecard's sparse shape.
    Gaps compare the furthest observed stage's displayed mark to its local
    qualifying cutoff; a mark at State has no gap. Missing or ambiguous source data leaves gaps
    unavailable. Each year is independent.
* qualifier_details maps Regional and State to rows with year, event,
    athlete_id, name, is_relay, mark, place, prelim and placer. Roster rows have
    athlete_id, name, grade, returning (True/False/None), regional_events and
    state_events. Returner/graduating lists contain the same roster row shape.
* data.event_cache_issues rows have year, event, missing and skipped_rows;
    unmatched_entries have year, event, athlete_id and is_relay. Completeness
    describes the selected years' caches and matches, not source-data coverage.
"""

import math
import os
import re
import threading
import zlib
from collections import OrderedDict, defaultdict
from types import FunctionType

from sqlalchemy.orm import joinedload

from common.const import CONST
from common.conversion import Conversion
from common.standards import get_state_standard, _STATE_STANDARD_VALUES
from .. import db
from ..models import Athlete, AthleteResult, Event, Meet, RelayResult, School
from ..queries.formatting import _format_gap_display, _format_result_display
from ..queries.school_dashboard import _covered_years, _event_groups
from ..queries import scorecard
from ..queries.meets import _compute_team_scores_for_meet
from ..queries.shared import (
    MIN_RECORDS_YEAR, REGIONAL_SECTIONAL_GROUPS, REGIONAL_TARGET_FIELD_SIZE, STATE_TARGET_FIELD_SIZE_BY_YEAR,
    _is_valid_postseason_mark, _resolve_school_enrollment_for_year,
    _school_logo_url, _select_preferred_result,
)
from common import cache_db


_RANKINGS_MEMO = {}


def _production_database():
    database = db.engine.url.database
    return bool(database) and database != ':memory:' and (
        os.path.normcase(os.path.realpath(database)) == os.path.normcase(os.path.realpath(CONST.DB_PATH)))


def _file_version(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


_SEASON_MEMO = OrderedDict()
_SEASON_MEMO_LOCK = threading.Lock()
# Most entries per kind, least recently used dropped first. The heavy kinds are
# per gender+season (4 = e.g. both teams for this season and last); dropping an
# older season only costs its next first view a rebuild.
_SEASON_MEMO_LIMITS = {'season_records': 4, '_individual_advancement': 4, '_relay_advancement': 4,
                       'distribution': 200, 'team_scores': 300}


def _data_version():
    """Changes whenever Track.db or the rankings cache is rebuilt."""
    return _file_version(CONST.DB_PATH), _file_version(cache_db.CACHE_DB_PATH)


def _memo(name, key, build):
    """Cache work that is the same for every school (statewide, per season).

    Only for the production database, keyed by its version, so a rebuilt
    database is never served stale and a test fixture never shares results.
    Each kind is capped (_SEASON_MEMO_LIMITS). Callers treat values as read-only.
    """
    if not _production_database():
        return build()
    full = (name, key, _data_version())
    with _SEASON_MEMO_LOCK:
        if full in _SEASON_MEMO:
            _SEASON_MEMO.move_to_end(full)
            return _SEASON_MEMO[full]
    value = build()  # outside the lock; two first visits may both build, harmlessly
    with _SEASON_MEMO_LOCK:
        _SEASON_MEMO[full] = value
        limit = _SEASON_MEMO_LIMITS.get(name, 200)
        same_kind = [k for k in _SEASON_MEMO if k[0] == name]
        for old in same_kind[:max(0, len(same_kind) - limit)]:
            del _SEASON_MEMO[old]
    return value


def _load_rankings(gender, year, event=''):
    """One precomputed ranked list, memoized until the cache file changes.

    A season page reads ~36 of these and All-Time ~130; each read otherwise
    opens the cache database and inflates the JSON again. Callers only read
    the returned rows, so sharing one decoded copy is safe.
    """
    if not _production_database():
        return None
    key = (gender, str(year), event or '', _file_version(cache_db.CACHE_DB_PATH))
    if key not in _RANKINGS_MEMO:
        if len(_RANKINGS_MEMO) > 2000:  # a rebuilt cache leaves stale keys behind
            _RANKINGS_MEMO.clear()
        _RANKINGS_MEMO[key] = cache_db.load_rankings(gender, str(year), event)
    return _RANKINGS_MEMO[key]


def _valid(value, field):
    return isinstance(value, (int, float)) and math.isfinite(value) and _is_valid_postseason_mark(value, 'Field' if field else 'Track')


def _school_rows(school_id, gender):
    """All school entries, including no-marks, with finals preferred per meet."""
    common = (Meet.gender == gender, Meet.year >= MIN_RECORDS_YEAR,
              Meet.meet_type.in_(CONST.MEET_TYPE.ALL))
    individuals = (db.session.query(AthleteResult, Athlete, Meet, Event.event_type)
        .join(Athlete, Athlete.athlete_id == AthleteResult.athlete_id)
        .join(Meet, Meet.meet_id == AthleteResult.meet_id)
        .join(Event, Event.event == AthleteResult.event)
        .filter(Athlete.school_id == school_id, Athlete.gender == gender, *common).all())
    relays = (db.session.query(RelayResult, Meet)
        .join(Meet, Meet.meet_id == RelayResult.meet_id)
        .filter(RelayResult.school_id == school_id, *common).all())
    chosen, best_round = {}, {}
    grades = defaultdict(set)
    for result, athlete, meet, event_type in individuals:
        key = (athlete.athlete_id, result.event, meet.meet_id)
        row = dict(athlete_id=athlete.athlete_id, name=f'{athlete.first or ""} {athlete.last or ""}'.strip(),
                   event=result.event, event_type=event_type, year=meet.year, meet_id=meet.meet_id,
                   meet_type=meet.meet_type, meet_num=meet.meet_num, result_type=result.result_type,
                   result=result.result, result_value=result.result2, place=result.place, is_relay=False)
        chosen[key] = _select_preferred_result(chosen.get(key), row)
        # Separately, the best valid mark from any round at this meet: it counts
        # for records, PRs and ranks even when it came from a prelim.
        field = event_type == 'Field'
        if _valid(result.result2, field):
            top = best_round.get(key)
            if top is None or (result.result2 > top[0] if field else result.result2 < top[0]) or (
                    result.result2 == top[0] and result.result_type == 'Final'):
                best_round[key] = (result.result2, result.result_type)
        if result.grade in ('FR', 'SO', 'JR', 'SR'):
            grades[(meet.year, athlete.athlete_id)].add(result.grade)
    # The meet's row (final first) decides places and advancement; best_value
    # and best_round carry the athlete's best mark there.
    for key, row in chosen.items():
        value, round_ = best_round.get(key, (None, None))
        row.update(best_value=value, best_round=round_)
    rows = list(chosen.values())
    for result, meet in relays:
        rows.append(dict(athlete_id=None, name='Relay', event=result.event, event_type='Relay',
                         year=meet.year, meet_id=meet.meet_id, meet_type=meet.meet_type,
                         meet_num=meet.meet_num, result_type='Final', result=result.result,
                         result_value=result.result2, place=result.place, is_relay=True,
                         best_value=result.result2, best_round='Final'))
    order = {'FR': 0, 'SO': 1, 'JR': 2, 'SR': 3}
    return rows, {key: max(value, key=order.get) for key, value in grades.items()}


def chart_events(events):
    """Only what the browser chart reads: values, our marks and the cuts.

    The full statewide rows (names, schools, ranks) are ~95% of the page and
    the chart never uses them.
    """
    def cut(items):
        return [dict(value=c['value'], mark=c['mark']) for c in items or []]
    return [dict(name=e['name'], unit=e['unit'], lower_is_better=e['lower_is_better'],
                 values=[round(m['value'], 2) for m in (e.get('distribution') or {}).get('marks') or []],
                 entries=[dict(value=x['value'], mark=x['mark'], name=x['name'], is_relay=x['is_relay'],
                               year=x.get('year')) for x in e.get('entries') or []],
                 regional_cutoff=cut(e.get('regional_cutoff')), state_cutoff=cut(e.get('state_cutoff')))
            for e in events]


def _best_entries(rows, grades):
    best = {}
    stages = defaultdict(set)
    furthest = {}
    for row in rows:
        key = (row['year'], row['event'], row['athlete_id'])
        stages[key].add(row['meet_type'])
        if key not in furthest or CONST.MEET_TYPE.ALL.index(row['meet_type']) > CONST.MEET_TYPE.ALL.index(furthest[key]['meet_type']):
            furthest[key] = row
        # Best mark from any round (best_value), so a prelim counts and a
        # scratched or DQ'd final does not erase a valid prelim.
        field = row['event_type'] == 'Field'
        value = row.get('best_value', row['result_value'])
        if not _valid(value, field):
            continue
        old = best.get(key)
        old_value = old.get('best_value', old['result_value']) if old else None
        if old is None or (value > old_value if field else value < old_value):
            best[key] = row
    entries = []
    for key, row in best.items():
        last = furthest[key]
        value = row.get('best_value', row['result_value'])
        entries.append(dict(event=row['event'], athlete_id=row['athlete_id'], name=row['name'],
            is_relay=row['is_relay'], year=row['year'], grade=grades.get((row['year'], row['athlete_id'])),
            # Format from the numeric value: raw results mix "5-8" and 5' 8" styles.
            mark=_format_result_display(value, row['event_type']),
            value=value, mark_prelim=row.get('best_round') == 'Prelim',
            meet_id=row['meet_id'], stage=row['meet_type'],
            place=last['place'], prelim=last['result_type'] == 'Prelim', final_stage=last['meet_type'],
            stages=[s for s in CONST.MEET_TYPE.ALL if s in stages[key]], rank=None,
            rank_total=None, percentile=None))
    return entries


def _cached_distribution(gender, years, event, field, all_time=False):
    """Best cached mark per athlete or relay school; missing years stay explicit.

    Statewide, so the same for every school: cached per data version (_memo).
    """
    return _memo('distribution', (gender, tuple(years), event, field, all_time),
                 lambda: _build_distribution(gender, years, event, field, all_time))


def _build_distribution(gender, years, event, field, all_time=False):
    best, missing = {}, []
    totals = {}
    skipped = 0
    for year in years:
        data = _load_rankings(gender, year, event)
        if not isinstance(data, dict) or not isinstance(data.get('rows'), list):
            missing.append(year)
            continue
        totals[year] = len(data['rows'])
        for row in data['rows']:
            identity = ('athlete', row.get('athlete_id')) if row.get('athlete_id') is not None else ('relay', row.get('school_id'))
            if identity[1] is None or not row.get('mark'):
                skipped += 1
                continue
            try:
                value = (Conversion.distance_to_inches(row['mark']) if field else Conversion.time_to_seconds(row['mark']))
            except (ValueError, TypeError):
                skipped += 1
                continue
            if not _valid(value, field):
                skipped += 1
                continue
            item = dict(value=value, mark=row['mark'], rank=row.get('rank'), name=row.get('name'),
                        athlete_id=row.get('athlete_id'), school_id=row.get('school_id'), year=year)
            old = best.get(identity)
            if old is None or (value > old['value'] if field else value < old['value']):
                best[identity] = item
    result = sorted(best.values(), key=lambda x: x['value'], reverse=field)
    if all_time:
        for row in result:
            row['rank'] = None  # annual ranks cannot be compared across years
    return {'marks': result, 'count': len(result), 'totals': totals, 'missing_years': missing,
            'skipped_rows': skipped, 'complete': not missing and not skipped}


def _field_size(stage, year):
    """Entrants per event at the next meet: 16 per regional; 27 at State
    through 2025 and 30 from 2026 on."""
    if stage == 'Sectional':
        return REGIONAL_TARGET_FIELD_SIZE
    return STATE_TARGET_FIELD_SIZE_BY_YEAR.get(year, 30 if year >= 2026 else 27)


def _rule_cut(finals, size, standard, field):
    """(value, place, path) of the advancement cut for one event's pool, or None.

    The top 3 of each final advance automatically; the remaining spots go to
    marks meeting the standard, and if those are too few, to the next-best
    marks. So the cut is the standard when it alone fills (or overfills) the
    spots, otherwise the mark in the last spot. None when the field could not
    be filled -- then every finalist advanced and there is no cut.
    """
    better = (lambda a, b: a >= b) if field else (lambda a, b: a <= b)
    automatic = sum(1 for r in finals if r['place'] <= 3)
    others = sorted((r for r in finals if r['place'] > 3 and _valid(r['value'], r['field'])),
                    key=lambda r: r['value'], reverse=field)
    spots = size - automatic
    meeting = sum(1 for r in others if standard is not None and better(r['value'], standard))
    if standard is not None and spots <= meeting:
        return standard, None, 'standard'
    if spots <= 0 or len(others) < spots:
        return None
    last = others[spots - 1]
    return last['value'], last['place'], 'fill'


def _season_records(gender, year):
    """Statewide meets and placed final marks for one season (same for every school)."""
    def build():
        regional_meets = [tuple(r) for r in db.session.query(Meet.meet_id, Meet.meet_num).filter(
            Meet.year == year, Meet.gender == gender, Meet.meet_type == 'Regional').all()]
        sectional_meets = [tuple(r) for r in db.session.query(Meet.meet_id, Meet.meet_num).filter(
            Meet.year == year, Meet.gender == gender, Meet.meet_type == 'Sectional').all()]
        individual = (db.session.query(AthleteResult.athlete_id, AthleteResult.event, AthleteResult.meet_id,
                        AthleteResult.place, AthleteResult.result2, AthleteResult.result_type,
                        Meet.meet_type, Event.event_type)
            .join(Meet, Meet.meet_id == AthleteResult.meet_id)
            .join(Athlete, Athlete.athlete_id == AthleteResult.athlete_id)
            .join(Event, Event.event == AthleteResult.event)
            .filter(Meet.year == year, Meet.gender == gender, Athlete.gender == gender,
                    Meet.meet_type.in_(CONST.MEET_TYPE.ALL)).all())
        relay = (db.session.query(RelayResult.school_id, RelayResult.event, RelayResult.meet_id,
                  RelayResult.place, RelayResult.result2, Meet.meet_type)
            .join(Meet, Meet.meet_id == RelayResult.meet_id)
            .filter(Meet.year == year, Meet.gender == gender, Meet.meet_type.in_(CONST.MEET_TYPE.ALL)).all())
        records = [dict(key=('athlete', r[0], r[1]), event=r[1], meet_id=r[2], place=r[3],
                        value=r[4], final=r[5] == 'Final', stage=r[6], field=r[7] == 'Field')
                   for r in individual]
        records += [dict(key=('relay', r[0], r[1]), event=r[1], meet_id=r[2], place=r[3],
                         value=r[4], final=True, stage=r[5], field=False) for r in relay]
        # Placed final marks by meet: what a cut's pool is built from.
        finals_by_meet = defaultdict(list)
        for row in records:
            if row['final'] and row['place'] and row['place'] > 0:
                finals_by_meet[row['meet_id']].append(row)
        return regional_meets, sectional_meets, records, dict(finals_by_meet)
    return _memo('season_records', (gender, year), build)


def _cutoffs(gender, year, school_rows):
    """Advancement cuts for the meets this school competed in.

    IHSAA rules (2023 on), the same at both steps: the top 3 in each final
    advance, plus anyone meeting that year's 3 Participant Standard; if too few
    meet it, the next-best marks fill the field (16 per regional, drawn from its
    four feeder sectionals; 27 at State through 2025 and 30 from 2026, drawn
    from all eight regionals).

    The cut is computed from every final mark in the pool by that rule (see
    _rule_cut), not from who actually showed up at the next meet: scratches
    and alternates would otherwise move it (e.g. a 13.36 alternate in a pool
    whose rule cut was 12.85).
    """
    sectionals = {r['meet_id'] for r in school_rows if r['meet_type'] == 'Sectional'}
    regional_ids = {r['meet_id'] for r in school_rows if r['meet_type'] == 'Regional'}
    sectional_numbers = {r['meet_id']: r['meet_num'] for r in school_rows if r['meet_type'] == 'Sectional'}
    sectional_nums = {r['meet_num'] for r in school_rows if r['meet_type'] == 'Sectional' and r['meet_num'] is not None}
    regional_nums = {number for number, feeders in REGIONAL_SECTIONAL_GROUPS.items()
                     if sectional_nums.intersection(feeders)}
    regional_meets, sectional_meets, _records, finals_by_meet = _season_records(gender, year)
    if len(regional_nums) == 1:
        regional_ids.update(m_id for m_id, num in regional_meets if num in regional_nums)
    # Each of our sectionals shares its pool (and so its cut) with every
    # sectional feeding the same regional.
    sectional_pools = {}
    for meet_id, number in sectional_numbers.items():
        mapped = [regional for regional, feeders in REGIONAL_SECTIONAL_GROUPS.items() if number in feeders]
        if len(mapped) == 1:
            feeders = REGIONAL_SECTIONAL_GROUPS[mapped[0]]
            sectional_pools[meet_id] = {m_id for m_id, num in sectional_meets if num in feeders} | {meet_id}
        else:
            # Without a known feeder group the pool is our sectional alone.
            sectional_pools[meet_id] = {meet_id}
    all_regionals = {m_id for m_id, _ in regional_meets} | regional_ids
    output = defaultdict(dict)
    for stage, meet_ids in (('Sectional', sectionals), ('Regional', regional_ids)):
        for meet_id in sorted(meet_ids):
            pool = sectional_pools[meet_id] if stage == 'Sectional' else all_regionals
            finals = defaultdict(list)
            for pool_meet in pool:
                for row in finals_by_meet.get(pool_meet, ()):
                    finals[row['event']].append(row)
            size = _field_size(stage, year)
            for group, names in _event_groups(gender):
                for event in names:
                    field = group in ('Jumps', 'Throws')
                    # get_state_standard falls back to another year's table; only use a listed year.
                    standard = get_state_standard(gender, event, year) if year in _STATE_STANDARD_VALUES else None
                    cut = _rule_cut(finals.get(event, []), size, standard, field)
                    if cut is not None:
                        value, place, path = cut
                        output[event].setdefault(stage, []).append(dict(value=value, place=place,
                            mark=_format_result_display(value, 'Field' if field else 'Track'),
                            meet_id=meet_id, path=path))
    return output


def _result_gap(row, source, cuts):
    """How far the athlete's last mark was from qualifying for the next round:
    a Sectional mark against its Regional cut (shown in the Regional column),
    a Regional mark against its State cut (shown in the State column). Only
    qualifying is measured, so a mark at State gets no gap."""
    for key in ('cutoff_display', 'cutoff_path', 'cutoff_value', 'gap_display', 'gap_value', 'gap_stage'):
        row[key] = None
    row['qualified_did_not_compete'] = row['tied_cutoff'] = False
    stages = row.get('stages') or {}
    if not stages or row.get('entry_type') == 'none':
        return
    stage = max(stages, key=CONST.MEET_TYPE.ALL.index)
    row['final_stage'] = stage
    cell = stages[stage]
    matching = [r for r in source if r['event'] == row['event']
                and r['athlete_id'] == row.get('athlete_id') and r['meet_type'] == stage]
    # Multiple meets in one stage cannot be reliably associated with a cell,
    # which carries no meet id. Do not select an arbitrary cutoff.
    if len(matching) != 1:
        return
    raw = matching[0]
    field = raw['event_type'] == 'Field'
    value = cell.get('result_value')
    if not cell.get('has_mark') or not _valid(value, field):
        return
    if stage == 'State':
        return  # nothing further to qualify for
    candidates = [cut for cut in cuts.get(row['event'], {}).get(stage, [])
                  if cut['meet_id'] == raw['meet_id'] and _valid(cut['value'], field)]
    if len(candidates) != 1:
        return
    cut = candidates[0]
    # A mark at or better than the cut has no "short by" (it may not have
    # counted, e.g. a prelim); report the cut but no gap.
    if (value >= cut['value']) if field else (value <= cut['value']):
        row.update(cutoff_display=cut['mark'], cutoff_path=cut['path'], cutoff_value=cut['value'])
        return
    gap = abs(value - cut['value'])
    gap_stage = {'Sectional': 'Regional', 'Regional': 'State'}.get(stage)
    row.update(cutoff_display=cut['mark'], cutoff_path=cut['path'], cutoff_value=cut['value'],
               gap_value=gap, gap_display=_format_gap_display(gap, 'Field' if field else 'Track'),
               gap_stage=gap_stage)


def _unit(row):
    return row['year'], row['event'], row['athlete_id']


def _placer(row, limit):
    return row['result_type'] == 'Final' and row['place'] is not None and 0 < row['place'] <= limit


def _pending_stages(gender, year):
    """Rounds with no results anywhere in the state yet that season for this
    gender, e.g. ['Regional', 'State'] right after Sectionals, or all three for
    boys between the girls' and boys' sectionals. The page shows these as
    pending, not as zero -- an empty round is "not run yet", not "nobody made it".
    """
    def build():
        held = set()
        for model in (AthleteResult, RelayResult):
            held.update(t for (t,) in db.session.query(Meet.meet_type).join(model, model.meet_id == Meet.meet_id)
                        .filter(Meet.year == year, Meet.gender == gender).distinct())
        return [stage for stage in ('Sectional', 'Regional', 'State') if stage not in held]
    return _memo('pending_stages', (gender, year), build)


def _season_summary(school_id, year, rows, ranking, with_teams=True):
    """Counts are athlete-events ("entries"). For display, *_athletes counts
    distinct individual athletes and *_relays counts relay entries: relay
    rosters are not recorded consistently (none from 2026), so a relay is
    reported as a relay, not as four people.

    with_teams=False skips team scoring (the slowest part), for seasons whose
    team finishes are not displayed.
    """
    def matching(stage, limit=None):
        return [r for r in rows if r['meet_type'] == stage and (limit is None or _placer(r, limit))]

    def count(stage, limit=None):
        return len({_unit(r) for r in matching(stage, limit)})

    def athletes(stage, limit=None):
        return len({r['athlete_id'] for r in matching(stage, limit) if not r['is_relay']})

    def relays(stage, limit=None):
        return len({_unit(r) for r in matching(stage, limit) if r['is_relay']})

    def team_for_stage(stage):
        if not with_teams:
            return None
        meet_ids = {r['meet_id'] for r in rows if r['meet_type'] == stage}
        if len(meet_ids) != 1:
            return None
        meet_id = next(iter(meet_ids))
        # The shared cache is keyed only by meet id, not database; bypass it here.
        scored = _memo('team_scores', meet_id, lambda: _compute_team_scores_for_meet.__wrapped__(meet_id)).get(school_id)
        if not scored:
            return None
        return dict(meet_id=meet_id, rank=scored['rank'], total_teams=scored['total_teams'], points=scored['points'])

    sectional_team = team_for_stage('Sectional')
    regional_team = team_for_stage('Regional')
    state_team = team_for_stage('State')
    valid_cache = isinstance(ranking, dict) and isinstance(ranking.get('rows'), list)
    rank_rows = ranking['rows'] if valid_cache else []
    details = {}
    # Sectional lists placers only; Regional and State list every qualifier.
    for stage, source in (('Sectional', matching('Sectional', 8)), ('Regional', matching('Regional')),
                          ('State', matching('State'))):
        details[stage] = [dict(year=r['year'], event=r['event'], athlete_id=r['athlete_id'],
                               name=r['name'], is_relay=r['is_relay'], mark=r['result'],
                               place=r['place'], prelim=r['result_type'] == 'Prelim',
                               placer=_placer(r, 9 if stage == 'State' else 8),
                               # Sort key for the mark column: lower is always better.
                               mark_order=(-r['result_value'] if r['event_type'] == 'Field' else r['result_value'])
                               if _valid(r['result_value'], r['event_type'] == 'Field') else None)
                          for r in source]
        # Best place first; unplaced entries last.
        details[stage].sort(key=lambda r: (r['place'] is None or r['place'] <= 0, r['place'] or 0,
                                           r['event'], r['name'], r['athlete_id'] or 0))
    medals = count('State', 9)
    sectional_champions = count('Sectional', 1)
    regional_champions = count('Regional', 1)
    state_champions = count('State', 1)
    sentence = (f'{medals} state medalist' + ('s' if medals != 1 else '') if medals else
                f'{sectional_champions} sectional champion' + ('s' if sectional_champions != 1 else '') if sectional_champions else None)
    return dict(year=year, result_units=len({_unit(r) for r in rows}),
                athletes=len({r['athlete_id'] for r in rows if not r['is_relay']}),
                sectional_placers=count('Sectional', 8), sectional_champions=sectional_champions,
                regional_entries=count('Regional'), regional_placers=count('Regional', 8),
                regional_champions=regional_champions,
                state_entries=count('State'), state_placers=medals, state_champions=state_champions,
                sectional_placer_athletes=athletes('Sectional', 8), sectional_placer_relays=relays('Sectional', 8),
                regional_qualifier_athletes=athletes('Regional'), regional_qualifier_relays=relays('Regional'),
                state_qualifier_athletes=athletes('State'), state_qualifier_relays=relays('State'),
                sectional_team=sectional_team, regional_team=regional_team, state_team=state_team,
                rank=next((dict(r) for r in rank_rows if r.get('school_id') == school_id), None),
                ranked_schools=len(rank_rows) if valid_cache else None,
                rank_cache_missing=not valid_cache, qualifier_details=details, sentence=sentence)


def _scorecard_without_live_rankings(school_id, gender, year):
    """Run the shared scorecard with isolated globals; do not mutate shared modules.

    Its API has no cache-only switch. A private function namespace avoids the
    statewide rank builders and cross-database lru caches, including under concurrent
    requests. The underlying scorecard still supplies the stage cells.
    """
    namespace = dict(scorecard.get_athlete_scorecard.__globals__)
    for name in ('_event_mark_ranks', '_relay_mark_ranks'):
        namespace[name] = lambda *_args: {}
    for name in ('_grades_for_season', '_individual_advancement', '_relay_advancement',
                 '_resolve_postseason_individual_rows', '_resolve_postseason_relay_rows'):
        func = namespace[name]
        namespace[name] = getattr(func, '__wrapped__', func)
    # Statewide advancement is the same for every school in a season. With the
    # production database it is cached by database version (_memo); with any
    # other database it is computed fresh, as above.
    for name in ('_individual_advancement', '_relay_advancement'):
        raw = namespace[name]
        namespace[name] = (lambda raw, name: lambda gender, year: _memo(name, (gender, year), lambda: raw(gender, year)))(raw, name)
    func = scorecard.get_athlete_scorecard
    return FunctionType(func.__code__, namespace, func.__name__, func.__defaults__, func.__closure__)(school_id, gender, str(year))


def _outlook(rows, grades, latest):
    people = {}
    for r in rows:
        if r['year'] != latest or r['is_relay']:
            continue
        grade = grades.get((latest, r['athlete_id']))
        person = people.setdefault(r['athlete_id'], dict(athlete_id=r['athlete_id'], name=r['name'],
                                  grade=grade, returning=grade in ('FR', 'SO', 'JR') if grade else None,
                                  regional_events=[], state_events=[], events=[], furthest='Sectional'))
        # Every postseason event, so sectional-only athletes still list theirs.
        if r['event'] not in person['events']:
            person['events'].append(r['event'])
        if CONST.MEET_TYPE.ALL.index(r['meet_type']) > CONST.MEET_TYPE.ALL.index(person['furthest']):
            person['furthest'] = r['meet_type']
        if r['meet_type'] in ('Regional', 'State'):
            events = person[r['meet_type'].lower() + '_events']
            if r['event'] not in events:
                events.append(r['event'])
    roster = sorted(people.values(), key=lambda r: (r['name'].lower(), r['athlete_id']))
    result = dict(year=latest, roster=roster,
                  returning_count=sum(r['returning'] is True for r in roster),
                  graduating_count=sum(r['returning'] is False for r in roster),
                  unknown_count=sum(r['returning'] is None for r in roster))
    for stage in ('regional', 'state'):
        for label, returning in (('returners', True), ('graduating', False)):
            result[f'{stage}_{label}'] = [r for r in roster if r['returning'] is returning and r[stage + '_events']]
    return result


def _size_group_rank(ranking, school_id):
    """The program's rank among same-size schools that season, or None.

    Schools split at the median enrollment of that season's ranked programs --
    the same split as the rankings popup's Small/Large switch, so the two agree.
    Ties share a rank (competition ranking, as in the full list).
    """
    rows = (ranking or {}).get('rows') if isinstance(ranking, dict) else None
    if not isinstance(rows, list):
        return None
    sizes = sorted(r['enrollment'] for r in rows
                   if isinstance(r.get('enrollment'), (int, float)) and r['enrollment'] > 0)
    mine = next((r for r in rows if r.get('school_id') == school_id), None)
    if not sizes or mine is None or not isinstance(mine.get('enrollment'), (int, float)) or mine.get('rank') is None:
        return None
    mid = len(sizes) // 2
    split = round(sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2)
    group = 'large' if mine['enrollment'] >= split else 'small'
    peers = [r for r in rows if isinstance(r.get('enrollment'), (int, float)) and r['enrollment'] > 0
             and (r['enrollment'] >= split) == (group == 'large') and r.get('rank') is not None]
    rank = 1 + sum(1 for r in peers if r['rank'] < mine['rank'])
    return dict(group=group, split=split, rank=rank, of=len(peers))


def _rank_all_time(entries, dist, school_id, field):
    """Rank entries against every Indiana athlete's best mark across all seasons.

    `dist` is the all-time distribution: one best mark per athlete (or relay
    school). Only an entry that IS that athlete's all-time best gets a rank;
    their slower seasons would otherwise be ranked against a field they are
    already in with a better mark.
    """
    marks = (dist or {}).get('marks') or []
    total = len(marks)
    for entry in entries:
        entry.update(all_time_rank=None, all_time_total=None, all_time_percentile=None)
        if not total:
            continue
        def is_own(mark):
            if entry['is_relay']:
                return mark['athlete_id'] is None and mark['school_id'] == school_id
            return mark['athlete_id'] == entry['athlete_id']
        own = next((m for m in marks if is_own(m)), None)
        if own is None or abs(own['value'] - entry['value']) > 1e-6:
            continue
        better = sum(1 for m in marks if (m['value'] > entry['value'] if field else m['value'] < entry['value']))
        entry.update(all_time_rank=better + 1, all_time_total=total, all_time_percentile=1 - better / total)


def _performance_order(entry):
    state = entry['final_stage'] == 'State'
    placer = state and not entry['prelim'] and entry['place'] is not None and 0 < entry['place'] <= 9
    return (0 if placer else 1 if state else 2, -entry['percentile'],
            entry['place'] if entry['place'] and entry['place'] > 0 else float('inf'),
            entry['name'].lower(), entry['event'], -entry['year'])


def build_payload(school_id, gender='Boys', season=None, with_results=True):
    """Return the documented payload, None for a missing school, or ValueError.

    with_results=False leaves results['rows'] empty on the All-Time view: the
    page does not show that table, and building it (a scorecard and cutoffs per
    season) is about half the All-Time cost. Season views always include it.
    """
    school = School.query.options(joinedload(School.enrollments)).filter_by(school_id=school_id).one_or_none()
    if school is None:
        return None
    gender = (gender or 'Boys').strip().title()
    if gender not in CONST.GENDER.ALL:
        raise ValueError('gender must be Boys or Girls')
    rows, grades = _school_rows(school_id, gender)
    years = sorted({year for choice in CONST.GENDER.ALL for year in _covered_years(choice)}, reverse=True)
    latest = max((r['year'] for r in rows), default=None)
    if season is None or season == '':
        selected = str(latest) if latest is not None else 'all-time'
    elif str(season).strip().lower() == 'all-time':
        selected = 'all-time'
    elif re.fullmatch(r'\d{4}', str(season).strip()) and int(season) in years:
        selected = str(int(season))
    else:
        raise ValueError('season must be all-time or a covered postseason year')
    all_time = selected == 'all-time'
    selected_years = years if all_time else [int(selected)]
    current = [r for r in rows if r['year'] in selected_years]
    entries = _best_entries(current, grades)
    records = _best_entries(rows, grades)
    annual_cache = {}
    history = []
    for year in years:
        ranking = _load_rankings(gender, year)
        annual_cache[year] = ranking
        # Team finishes for other seasons are shown only on the All-Time page.
        history.append(_season_summary(school_id, year, [r for r in rows if r['year'] == year], ranking,
                                       with_teams=all_time or str(year) == selected))
        history[-1]['size_rank'] = _size_group_rank(ranking, school_id)
        history[-1]['pending'] = _pending_stages(gender, year)
    if all_time:
        summary = _season_summary(school_id, None, current, None)
        summary.update(sectional_team=None, regional_team=None, state_team=None,
                       rank=None, ranked_schools=None, rank_cache_missing=False)
    else:
        summary = dict(next(h for h in history if h['year'] == int(selected)))
    build_results = with_results or not all_time
    cuts_by_year = {year: _cutoffs(gender, year, [r for r in current if r['year'] == year])
                    for year in (selected_years if build_results else [])}
    cuts = {} if all_time else cuts_by_year[int(selected)]
    events, bests, annual_distributions = [], [], {}
    missing_events, unmatched_entries = [], []
    for group, names in _event_groups(gender):
        for name in names:
            field = group in ('Jumps', 'Throws')
            for year in selected_years:
                dist = _cached_distribution(gender, [year], name, field)
                annual_distributions[(year, name)] = dist
                if not dist['complete']:
                    missing_events.append(dict(year=year, event=name, missing=bool(dist['missing_years']), skipped_rows=dist['skipped_rows']))
            for entry in (e for e in entries if e['event'] == name):
                dist = annual_distributions[(entry['year'], name)]
                match = next((r for r in dist['marks'] if
                    (r['school_id'] == school_id if entry['is_relay'] else r['athlete_id'] == entry['athlete_id'])
                    and abs(r['value'] - entry['value']) < 1e-6), None)
                total = dist['totals'].get(entry['year'])
                rank = match['rank'] if match else None
                if isinstance(rank, int) and total and 1 <= rank <= total:
                    entry.update(rank=rank, rank_total=total, percentile=1 - (rank - 1) / total)
                elif not dist['missing_years']:
                    unmatched_entries.append(dict(year=entry['year'], event=name,
                                                  athlete_id=entry['athlete_id'], is_relay=entry['is_relay']))
            event_entries = sorted((e for e in entries if e['event'] == name), key=lambda x: x['value'], reverse=field)
            # A single season's chart is the per-year distribution built above.
            dist = (_cached_distribution(gender, selected_years, name, field, all_time) if all_time
                    else annual_distributions[(selected_years[0], name)])
            if all_time:
                _rank_all_time(event_entries, dist, school_id, field)
            event_cuts = cuts.get(name, {})
            events.append(dict(name=name, label=name, group=group, unit='inches' if field else 'seconds',
                lower_is_better=not field, entries=event_entries, distribution=dist,
                regional_cutoff=event_cuts.get('Sectional', []), state_cutoff=event_cuts.get('Regional', [])))
            candidates = [e for e in records if e['event'] == name]
            best_value = (max if field else min)((e['value'] for e in candidates), default=None)
            bests.append(dict(event=name, entries=[e for e in candidates if e['value'] == best_value]))
    unique = {}
    if all_time:
        # All-time: each athlete's (or relay's) best mark ranked against every
        # Indiana athlete's best across all covered seasons -- not a single
        # season's rank. One card per athlete, their best all-time standing.
        for entry in entries:
            if entry.get('all_time_percentile') is None:
                continue
            key = ('relay', entry['event']) if entry['is_relay'] else ('athlete', entry['athlete_id'])
            old = unique.get(key)
            if old is None or entry['all_time_percentile'] > old['all_time_percentile']:
                unique[key] = entry
        summary['top_performers'] = sorted(
            unique.values(), key=lambda e: (-e['all_time_percentile'], e['all_time_rank'], e['event'], e['name']))[:10]
    else:
        for entry in entries:
            if entry['percentile'] is None:
                continue
            key = ('relay', entry['event']) if entry['is_relay'] else ('athlete', entry['athlete_id'])
            old = unique.get(key)
            if old is None or entry['percentile'] > old['percentile'] or (
                    entry['percentile'] == old['percentile'] and _performance_order(entry) < _performance_order(old)):
                unique[key] = entry
        summary['top_performers'] = sorted(unique.values(), key=_performance_order)[:10]
    results = dict(stages=[], rows=[])
    entry_lookup = {(e['year'], e['event'], e['athlete_id']): e for e in entries}
    for year in (selected_years if build_results else []):
        card = _scorecard_without_live_rankings(school_id, gender, year)
        source = [r for r in current if r['year'] == year]
        card_rows = card['rows']
        card_by_unit = {(r['event'], r.get('athlete_id')): r for r in card_rows if r.get('entry_type') != 'none'}
        for raw in source:
            key = (raw['event'], raw['athlete_id'])
            row = card_by_unit.get(key)
            if row is None:
                row = dict(event=raw['event'], entry_type='relay' if raw['is_relay'] else 'individual',
                           athlete_id=raw['athlete_id'], name=raw['name'], grade=grades.get((year, raw['athlete_id'])),
                           stages={}, best_stage=None, mark_display=None, result_value=None,
                           cutoff_display=None, cutoff_path=None, gap_display=None, cutoff_value=None,
                           gap_value=None, qualified_did_not_compete=False, tied_cutoff=False)
                card_rows[:] = [r for r in card_rows if not (r['event'] == raw['event'] and r.get('entry_type') == 'none')]
                card_rows.append(row)
                card_by_unit[key] = row
            cell = row['stages'].get(raw['meet_type'])
            if cell is None or (raw['result_type'] == 'Final' and cell.get('round') != 'Final'):
                has_mark = _valid(raw['result_value'], raw['event_type'] == 'Field')
                row['stages'][raw['meet_type']] = dict(mark_display=raw['result'],
                    result_value=raw['result_value'] if has_mark else None, has_mark=has_mark,
                    place=raw['place'] if raw['place'] and raw['place'] > 0 else None,
                    round=raw['result_type'])
                # The shared advancement query did not see this source row; its
                # cutoff/gap may describe a different round or a prelim.
                for key_name in ('cutoff_display', 'cutoff_path', 'cutoff_value', 'gap_display', 'gap_value'):
                    row[key_name] = None
                row['qualified_did_not_compete'] = row['tied_cutoff'] = False
            row['final_stage'] = max(row['stages'], key=CONST.MEET_TYPE.ALL.index)
            if raw['meet_type'] not in card['stages_present']:
                card['stages_present'].append(raw['meet_type'])
        for stage in card['stages_present']:
            if stage not in results['stages']:
                results['stages'].append(stage)
        for row in card['rows']:
            row = dict(row, year=year)
            entry = entry_lookup.get((year, row['event'], row.get('athlete_id'))) if row.get('entry_type') != 'none' else None
            row['rank'] = entry['rank'] if entry else None
            row['rank_total'] = entry['rank_total'] if entry else None
            if entry:
                row['best_stage'], row['mark_display'], row['result_value'] = entry['stage'], entry['mark'], entry['value']
            elif row.get('entry_type') != 'none':
                row['best_stage'], row['mark_display'], row['result_value'] = None, None, None
            _result_gap(row, source, cuts_by_year[year])
            row['gap'] = row.get('gap_display')
            results['rows'].append(row)
    results['stages'].sort(key=CONST.MEET_TYPE.ALL.index)
    program_missing = [y for y in selected_years if not isinstance(annual_cache[y], dict) or not isinstance(annual_cache[y].get('rows'), list)]
    enrollment = _resolve_school_enrollment_for_year(school, None if all_time else int(selected))
    return dict(school=dict(id=school.school_id, name=school.school_name, city=school.city,
                    school_type=school.school_type, logo_url=_school_logo_url(school),
                    enrollment=enrollment['value'], enrollment_source_year=enrollment['source_year'],
                    enrollment_is_exact=enrollment['is_exact']),
        gender=gender, season=selected, years=years, is_all_time=all_time, latest_year=latest,
        summary=summary, performances=entries, events=events, results=results,
        outlook=_outlook(rows, grades, latest), history=history, bests=bests,
        data=dict(program_missing_years=program_missing, event_cache_issues=missing_events,
              unmatched_entries=unmatched_entries,
              complete=not program_missing and not missing_events and not unmatched_entries))

_PAGE_CACHE = OrderedDict()
_PAGE_CACHE_SIZE = 256
_PAGE_CACHE_LOCK = threading.Lock()


# ----------------------------------------------------------- stored pages
# School pages are precomputed (app.jobs.precompute_school_pages) into
# dashboard_cache.db (common/cache_db.py), because PythonAnywhere runs this analysis 15-25x slower
# than a development machine. Stored without the statewide distribution curves --
# identical for every school -- which are restored at request time from the
# rankings already in memory. Bump PAGE_FORMAT whenever the payload's shape
# changes: stored pages of another format are ignored (built live) until rebuilt.
PAGE_FORMAT = '1'


def allow_live_build(app):
    """Development builds pages live, so code and template changes show at once:
    debug mode, or TI_LIVE_DASHBOARD=1. Never on the deployed site, where a live
    build takes seconds per page."""
    if os.environ.get('TI_LIVE_DASHBOARD') == '1':
        return True
    return bool(app.debug)


def slim_payload(payload):
    """The payload as stored: without the statewide distributions."""
    return dict(payload, events=[{k: v for k, v in e.items() if k != 'distribution'}
                                 for e in payload.get('events') or []])


def _restore_payload(payload):
    """Put the statewide distributions back (season pages draw them; All-Time does not)."""
    groups = dict((name, group) for group, names in _event_groups(payload['gender']) for name in names)
    year = None if payload.get('is_all_time') else int(payload['season'])
    for event in payload.get('events') or []:
        field = groups.get(event['name']) in ('Jumps', 'Throws')
        event['distribution'] = {} if year is None else _cached_distribution(payload['gender'], [year], event['name'], field)
    return payload


def write_school_pages(rows, views):
    """Replace the stored pages for the given views ('2026', 'all-time', ...) in one transaction."""
    conn = cache_db.connect(readonly=False)
    try:
        with conn:
            conn.executemany('DELETE FROM school_pages WHERE season=?', [(v,) for v in views])
            conn.executemany('INSERT INTO school_pages (school_id, gender, season, payload) VALUES (?, ?, ?, ?)', rows)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('school_pages_format', ?)", (PAGE_FORMAT,))
    finally:
        conn.close()


def _use_stored_pages():
    """The deployed site reads stored pages; development builds live so code
    changes show at once. Never for a fixture database."""
    from flask import current_app
    return _production_database() and not allow_live_build(current_app)


def _default_season(school_id, gender):
    """The season a bare /school-dashboard/<id> shows: the school's latest with results
    (the same rule as build_payload), else All-Time."""
    common = (Meet.gender == gender, Meet.year >= MIN_RECORDS_YEAR, Meet.meet_type.in_(CONST.MEET_TYPE.ALL))
    individual = (db.session.query(db.func.max(Meet.year)).select_from(AthleteResult)
                  .join(Athlete, Athlete.athlete_id == AthleteResult.athlete_id)
                  .join(Meet, Meet.meet_id == AthleteResult.meet_id)
                  .filter(Athlete.school_id == school_id, Athlete.gender == gender, *common).scalar())
    relay = (db.session.query(db.func.max(Meet.year)).select_from(RelayResult)
             .join(Meet, Meet.meet_id == RelayResult.meet_id)
             .filter(RelayResult.school_id == school_id, *common).scalar())
    latest = max((y for y in (individual, relay) if y is not None), default=None)
    return str(latest) if latest is not None else 'all-time'


# The parts of a season page that cover every season, not just its own: the
# season picker, the season-by-season history, program records and returners.
# A build refreshes only the seasons it is given (normally the current one) plus
# All-Time, so a stored 2026 page would otherwise never learn about 2027. They
# are identical on every view of a school, so a season page takes them from
# the school's All-Time page, which every build refreshes.
_ALL_SEASON_KEYS = ('years', 'history', 'bests', 'latest_year', 'outlook')


def _stored_page(school_id, gender, season):
    """A stored payload, restored, or None (not stored, other format, or no cache)."""
    import sqlite3
    try:
        conn = cache_db.connect(readonly=True)
    except sqlite3.OperationalError:
        return None
    query = 'SELECT payload FROM school_pages WHERE school_id=? AND gender=? AND season=?'
    try:
        fmt = conn.execute("SELECT value FROM meta WHERE key='school_pages_format'").fetchone()
        if not fmt or fmt[0] != PAGE_FORMAT:
            return None
        row = conn.execute(query, (school_id, gender, season)).fetchone()
        overview = (conn.execute(query, (school_id, gender, 'all-time')).fetchone()
                    if row and season != 'all-time' else None)
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    payload = cache_db.decode(row[0]) if row else None
    if not isinstance(payload, dict):
        return None
    current = cache_db.decode(overview[0]) if overview else None
    if isinstance(current, dict):
        payload.update({key: current[key] for key in _ALL_SEASON_KEYS if key in current})
    return _restore_payload(payload)


def page_data(school_id, gender=None, season=None):
    """(payload, chart_events) for the school page; (None, None) for a missing
    school; ValueError for a bad gender or season.

    On the deployed site this reads the stored page; a page that is not stored
    (a new school, an unbuilt season) is built live. Not cached here (see page_html).
    """
    if _use_stored_pages():
        team = (gender or 'Boys').strip().title()
        view = str(season or '').strip().lower()
        if team in CONST.GENDER.ALL:
            if not view:
                view = _default_season(school_id, team)
            payload = _stored_page(school_id, team, view)
            if payload is not None:
                charts = [] if payload.get('is_all_time') else chart_events(payload.get('events') or [])
                return payload, charts
    all_time = str(season or '').strip().lower() == 'all-time'
    payload = build_payload(school_id, gender or 'Boys', season, with_results=not all_time)
    if payload is None:
        return None, None
    charts = [] if payload.get('is_all_time') else chart_events(payload.get('events') or [])
    return payload, charts


def page_html(school_id, gender, season, render):
    """The school page's finished HTML, cached until the data changes.

    render(payload, charts) -> str. What is cached is the rendered page,
    zlib-compressed (~30KB a page, vs ~440KB for the page's data), in a small
    LRU keyed by the data version: a rebuilt Track.db or rankings cache is
    never served stale. A fixture or in-memory database is never cached.
    Returns None for a missing school; raises ValueError like build_payload.
    """
    def build():
        payload, charts = page_data(school_id, gender, season)
        return None if payload is None else render(payload, charts)

    # Development renders every time: a template edit must show on refresh,
    # and the key below only tracks the data, not the template.
    from flask import current_app
    if not _production_database() or allow_live_build(current_app):
        return build()
    key = (school_id, (gender or 'Boys').strip().title(), str(season or '')) + _data_version()
    with _PAGE_CACHE_LOCK:
        if key in _PAGE_CACHE:
            _PAGE_CACHE.move_to_end(key)
            blob = _PAGE_CACHE[key]
            return None if blob is None else zlib.decompress(blob).decode('utf-8')
    html = build()
    with _PAGE_CACHE_LOCK:
        _PAGE_CACHE[key] = None if html is None else zlib.compress(html.encode('utf-8'), 6)
        while len(_PAGE_CACHE) > _PAGE_CACHE_SIZE:
            _PAGE_CACHE.popitem(last=False)
    return html


_ALL_TIME_LISTS = {}


def all_time_rankings(gender, event):
    """One event's all-time list: every athlete's (or relay's) best mark across
    every covered season, competition-ranked. The basis of the All-Time ranks
    on the school page, so a card opens the list its rank came from.

    Built from the per-season lists in the rankings cache; None when the cache
    is unavailable (e.g. a fixture database). Enrollment is the school's most
    recent value. Memoized until the cache file changes.
    """
    gender = (gender or '').strip().title()
    if gender not in CONST.GENDER.ALL or not event:
        return None
    groups = dict((name, group) for group, names in _event_groups(gender) for name in names)
    if event not in groups:
        return None
    field = groups[event] in ('Jumps', 'Throws')
    key = (gender, event, _file_version(cache_db.CACHE_DB_PATH))
    if key in _ALL_TIME_LISTS:
        return _ALL_TIME_LISTS[key]
    best, enrollment, seasons = {}, {}, []
    for year in sorted(_covered_years(gender)):
        data = _load_rankings(gender, year, event)
        if not isinstance(data, dict) or not isinstance(data.get('rows'), list):
            continue
        seasons.append(year)
        for row in data['rows']:
            identity = ('athlete', row.get('athlete_id')) if row.get('athlete_id') is not None else ('relay', row.get('school_id'))
            if identity[1] is None or not row.get('mark'):
                continue
            try:
                value = Conversion.distance_to_inches(row['mark']) if field else Conversion.time_to_seconds(row['mark'])
            except (ValueError, TypeError):
                continue
            if not _valid(value, field):
                continue
            if row.get('school_id') is not None and row.get('enrollment') is not None:
                enrollment[row['school_id']] = row['enrollment']  # later seasons overwrite
            old = best.get(identity)
            if old is None or (value > old['value'] if field else value < old['value']):
                best[identity] = dict(row, value=value, year=year)
    if not best:
        return None
    ordered = sorted(best.values(), key=lambda r: r['value'], reverse=field)
    rows, previous, rank = [], None, 0
    for index, row in enumerate(ordered, start=1):
        if row['value'] != previous:
            rank, previous = index, row['value']
        rows.append(dict(rank=rank, athlete_id=row.get('athlete_id'), name=row.get('name'),
                         school_id=row.get('school_id'), school=row.get('school'), mark=row.get('mark'),
                         year=row['year'], grade=row.get('grade'), enrollment=enrollment.get(row.get('school_id'), row.get('enrollment'))))
    relay = groups[event] == 'Relays'
    payload = dict(kind='event', title=f'{event} · All-Time',
                   subtitle=f"{gender} {seasons[0]}–{seasons[-1]} — {len(rows):,} {'relays' if relay else 'athletes'} ranked, best mark each",
                   columns=['Rank', 'Relay' if relay else 'Athlete', 'School', 'Mark', 'Year', 'Enrollment'],
                   rows=rows, latest_season=str(seasons[-1]))
    if len(_ALL_TIME_LISTS) > 200:
        _ALL_TIME_LISTS.clear()
    _ALL_TIME_LISTS[key] = payload
    return payload
