"""Team scoring: the points table, and how a tie splits.

This is the trickiest arithmetic in the project and the most consequential -- it
decides the team totals and the program rankings built on top of them -- and it
was reachable only through page-level smoke tests. These exercise it directly.

The rule: tied entries share the combined value of the scoring slots they
occupy. Two schools tied for 3rd take slots 3 and 4, so each gets (6+5)/2 = 5.5
rather than 6 apiece. A tie that runs off the end of the table shares only the
slots that actually score.

Sectional and Regional score the top 8 (10-8-6-5-4-3-2-1); State scores the top 9
with a different shape (10-8-7-6-5-4-3-2-1) -- 3rd at State is worth 7, not 6.
"""
import pytest

from app import db
from app.models import Athlete, AthleteResult, Meet, School
from app.queries import _clear_query_caches
from app.queries.meets import _compute_cumulative_points

# Kept clear of the ids conftest seeds.
BASE_SCHOOL = 900
BASE_ATHLETE = 9000
BASE_MEET = 900

EVENT = "100 Meters"
YEAR = 2024


def _scenario(meet_type, places):
    """Seed one meet in which each school takes one of `places` in one event.

    `places` is {school_offset: place}. Returns the points each school scored.
    """
    meet_id = BASE_MEET + {'Sectional': 1, 'Regional': 2, 'State': 3}[meet_type]
    db.session.add(Meet(meet_id=meet_id, host='Scoring Test', meet_type=meet_type,
                        meet_num=1, gender='Boys', year=YEAR))

    for offset, place in places.items():
        school_id = BASE_SCHOOL + offset
        athlete_id = BASE_ATHLETE + offset
        db.session.add(School(school_id=school_id, school_name='Scoring %d' % offset,
                              team_name='Scoring %d' % offset, school_type='Public'))
        db.session.add(Athlete(athlete_id=athlete_id, first='Scorer', last=str(offset),
                               school_id=school_id, gender='Boys', graduation_year=2025))
        db.session.add(AthleteResult(athlete_id=athlete_id, meet_id=meet_id, event=EVENT,
                                     result_type='Final', result='11.00', result2=11.0,
                                     place=place, grade='SR'))
    db.session.commit()
    _clear_query_caches()

    stage = meet_type.lower()
    return {offset: _points_for(BASE_SCHOOL + offset, stage) for offset in places}


def _points_for(school_id, stage):
    """The points one school scored at `stage` in YEAR.

    _compute_cumulative_points returns {gender: {"yearly": [...], "grand_total": n}},
    one entry per season, each split into sectional / regional / state.
    """
    payload = _compute_cumulative_points(school_id)
    for row in payload.get('Boys', {}).get('yearly', []):
        if row.get('year') == YEAR:
            return row[stage]['points']
    return 0


def test_untied_places_take_the_table_verbatim(app):
    with app.app_context():
        points = _scenario('Sectional', {1: 1, 2: 2, 3: 3, 4: 4})
    assert points == {1: 10, 2: 8, 3: 6, 4: 5}


def test_two_schools_tied_for_third_split_slots_three_and_four(app):
    """(6 + 5) / 2 = 5.5 each -- not 6 each, which would invent a point."""
    with app.app_context():
        points = _scenario('Sectional', {1: 1, 2: 2, 3: 3, 4: 3})
    assert points[3] == pytest.approx(5.5)
    assert points[4] == pytest.approx(5.5)


def test_a_three_way_tie_for_first_shares_the_top_three_slots(app):
    """(10 + 8 + 6) / 3 = 8 each."""
    with app.app_context():
        points = _scenario('Sectional', {1: 1, 2: 1, 3: 1})
    for offset in (1, 2, 3):
        assert points[offset] == pytest.approx(8.0)


def test_a_tie_running_past_the_last_scoring_place_shares_only_what_scores(app):
    """Two tied for 8th at a sectional: slot 8 scores 1, slot 9 does not exist.

    So they share a single point, half each, rather than each taking one.
    """
    with app.app_context():
        points = _scenario('Sectional', {1: 8, 2: 8})
    assert points[1] == pytest.approx(0.5)
    assert points[2] == pytest.approx(0.5)


def test_a_tie_entirely_outside_the_table_scores_nothing(app):
    with app.app_context():
        points = _scenario('Sectional', {1: 9, 2: 9})
    assert points[1] == 0
    assert points[2] == 0


def test_state_uses_its_own_table_where_third_is_worth_seven(app):
    """State scores nine places and 3rd is 7 -- at a sectional it would be 6."""
    with app.app_context():
        points = _scenario('State', {1: 1, 2: 2, 3: 3, 4: 9})
    assert points == {1: 10, 2: 8, 3: 7, 4: 1}


def test_ninth_place_scores_at_state_but_not_at_a_regional(app):
    with app.app_context():
        regional = _scenario('Regional', {1: 9})
    assert regional[1] == 0


def test_the_same_place_in_two_events_is_not_a_tie(app):
    """Two schools each 1st, in different events, both take the full 10.

    Ties are per event. Grouping by place alone across a whole meet would have
    split these -- which is the mistake the (meet, event) key exists to prevent.
    """
    with app.app_context():
        meet_id = BASE_MEET + 7
        db.session.add(Meet(meet_id=meet_id, host='Two Events', meet_type='Sectional',
                            meet_num=1, gender='Boys', year=YEAR))
        for offset, event in ((1, '100 Meters'), (2, '200 Meters')):
            db.session.add(School(school_id=BASE_SCHOOL + offset,
                                  school_name='Ev %d' % offset,
                                  team_name='Ev %d' % offset, school_type='Public'))
            db.session.add(Athlete(athlete_id=BASE_ATHLETE + offset, first='Ev',
                                   last=str(offset), school_id=BASE_SCHOOL + offset,
                                   gender='Boys', graduation_year=2025))
            db.session.add(AthleteResult(athlete_id=BASE_ATHLETE + offset, meet_id=meet_id,
                                         event=event, result_type='Final', result='11.00',
                                         result2=11.0, place=1, grade='SR'))
        db.session.commit()
        _clear_query_caches()

        for offset in (1, 2):
            assert _points_for(BASE_SCHOOL + offset, 'sectional') == 10, (
                'school %d' % offset)


def test_the_table_matches_the_standalone_implementation():
    """The two copies of the rules agree.

    web/app/queries/shared.py and standalone/scripts/calculate_team_scores.py
    each spell out the points tables. They are supposed to be the same rules;
    this fails if one is edited without the other.
    """
    import ast
    import os

    from app.queries.shared import _PLACE_POINTS, _STATE_PLACE_POINTS

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'standalone', 'scripts', 'calculate_team_scores.py')
    with open(script, encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), filename=script)

    tables = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith('SCORING'):
                    tables[target.id] = ast.literal_eval(node.value)

    assert tables.get('STATE_SCORING') == _STATE_PLACE_POINTS, (
        'the State points tables have diverged')
    assert tables.get('SECTIONAL_REGIONAL_SCORING') == _PLACE_POINTS, (
        'the Sectional/Regional points tables have diverged')
