import json
import os
from flask import jsonify, request, current_app
from . import api_bp
from common.const import CONST
from ..queries import (
    get_athletes,
    get_athlete_by_id,
    add_athlete,
    search_bar,
    get_athlete_dashboard_data,
    get_athlete_result_rankings,
    get_percentile_options,
    get_percentiles_report,
    get_sectional_event_trends_options,
    get_sectional_event_trends,
    get_hypothetical_ranking_options,
    get_hypothetical_result_rankings,
    get_school_dashboard_data,
    get_school_dashboard_v2_core,
    get_school_dashboard_v2_event_detail,
    get_school_dashboard_v2_leaderboard,
    get_school_dashboard_v3_scorecard,
    get_school_dashboard_v3_athlete_scorecard,
    get_school_dashboard_v3_program_rank,
    get_school_dashboard_v3_season_h2h,
    get_school_dashboard_v3_event_rankings,
    get_school_dashboard_v3_returning,
    get_school_dashboard_v3_season_status,
    _school_dashboard_v3_stage_deltas as get_school_dashboard_v3_stage_deltas,
    _compute_school_percentiles,
    get_regional_qualifiers_status,
    get_regional_qualifiers,
    get_state_qualifiers_status,
    get_state_qualifiers,
)


@api_bp.route('/athletes')
def api_get_athletes():
    athletes = get_athletes(50)
    return jsonify([{
        'id': a.athlete_id, 
        'first_name': a.first, 
        'last_name': a.last, 
        'school': a.school.school_name if a.school else None
    } for a in athletes])


@api_bp.route('/athletes/<int:aid>')
def api_get_athlete(aid):
    a = get_athlete_by_id(aid)
    if not a:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'id': a.athlete_id, 
        'first_name': a.first, 
        'last_name': a.last,
        'graduation_year':a.graduation_year,
        'school': a.school.school_name if a.school else None
        
    })


@api_bp.route('/athletes', methods=['POST'])
def api_add_athlete():
    data = request.get_json() or {}
    fn = data.get('first_name')
    ln = data.get('last_name')
    if not fn or not ln:
        return jsonify({'error': 'first_name and last_name required'}), 400
    a = add_athlete(
        fn,
        ln,
        school=data.get('school'),
        gender=data.get('gender'),
        graduation_year=data.get('graduation_year'),
    )
    return jsonify({'id': a.athlete_id}), 201


@api_bp.route('/search')
def api_search_bar():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    results = search_bar(query)
    return jsonify(results)


@api_bp.route('/athletes/<int:aid>/dashboard')
def api_get_athlete_dashboard(aid):
    data = get_athlete_dashboard_data(aid)
    if not data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)


@api_bp.route('/athletes/<int:aid>/result-rankings')
def api_get_result_rankings(aid):
    meet_id = request.args.get('meet_id', type=int)
    event = request.args.get('event')
    result_type = request.args.get('result_type', default='Final')

    if not meet_id or not event:
        return jsonify({'error': 'meet_id and event are required'}), 400

    data = get_athlete_result_rankings(aid, meet_id, event, result_type=result_type)
    if not data:
        return jsonify({'error': 'not found'}), 404

    return jsonify(data)


def _parse_multi_value(param_name, cast=str):
    values = request.args.getlist(param_name)
    if not values:
        raw_value = request.args.get(param_name)
        if raw_value:
            values = [raw_value]

    normalized = []
    for entry in values:
        if entry is None:
            continue
        for piece in str(entry).replace(';', ',').split(','):
            piece = piece.strip()
            if not piece:
                continue
            try:
                normalized.append(cast(piece))
            except ValueError as exc:
                raise ValueError(f"Invalid value '{piece}' for {param_name}") from exc

    return tuple(normalized) if normalized else None


@api_bp.route('/percentiles/options')
def api_percentile_options():
    data = get_percentile_options()
    return jsonify(data)


@api_bp.route('/percentiles')
def api_percentiles():
    try:
        filters = {
            'events': _parse_multi_value('events'),
            'genders': _parse_multi_value('genders'),
            'percentiles': _parse_multi_value('percentiles', int),
            'years': _parse_multi_value('years', int),
            'meet_types': _parse_multi_value('meet_types'),
            'grade_levels': _parse_multi_value('grade_levels', lambda value: value.upper()),
        }
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        payload = get_percentiles_report(**filters)
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify(payload)


@api_bp.route('/sectional-trends/options')
def api_sectional_trends_options():
    """Return filter options for sectional event trends."""
    try:
        data = get_sectional_event_trends_options()
        return jsonify(data)
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/sectional-trends')
def api_sectional_trends():
    """Return sectional event trends data for a given gender and event."""
    gender = request.args.get('gender', '').strip()
    event = request.args.get('event', '').strip()
    
    if not gender or not event:
        return jsonify({'error': 'gender and event are required'}), 400
    
    try:
        payload = get_sectional_event_trends(gender, event)
        return jsonify(payload)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/hypothetical-rank/options')
def api_hypothetical_rank_options():
    """Return filter options for the hypothetical athlete query."""
    try:
        data = get_hypothetical_ranking_options()
        return jsonify(data)
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/hypothetical-rank')
def api_hypothetical_rank():
    """Return ranking data for a hypothetical performance."""
    event = request.args.get('event', '').strip()
    time = request.args.get('time', '').strip()
    gender = request.args.get('gender', '').strip()
    year = request.args.get('year', type=int)
    meet_type = request.args.get('meet_type', 'Sectional').strip()
    enrollment = request.args.get('enrollment', type=int)
    grade_level = request.args.get('grade_level', '').strip() or None

    if not event or not time or not gender or not year:
        return jsonify({'error': 'event, time, gender, and year are required'}), 400

    try:
        data = get_hypothetical_result_rankings(
            event_name=event,
            performance_input=time,
            gender=gender,
            year=year,
            meet_type=meet_type,
            enrollment=enrollment,
            grade_level=grade_level,
        )
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    if not data:
        return jsonify({'error': 'No data found for the given parameters'}), 404

    return jsonify(data)


@api_bp.route('/schools/<int:school_id>/dashboard')
def api_get_school_dashboard(school_id):
    data = get_school_dashboard_data(school_id)
    if not data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)


@api_bp.route('/schools/<int:school_id>/percentiles')
def api_get_school_percentiles(school_id):
    """Return school percentiles, optionally filtered to a single year."""
    year = request.args.get('year', type=int)
    results = _compute_school_percentiles(school_id, year=year)
    return jsonify(results)


@api_bp.route('/regional-qualifiers/status')
def api_regional_qualifiers_status():
    """Return regional readiness status for a gender and year."""
    gender = request.args.get('gender', 'Boys').strip()
    year = request.args.get('year', default=2026, type=int)
    if year is None or year < 2000:
        return jsonify({'error': 'year must be a valid season year'}), 400

    try:
        payload = get_regional_qualifiers_status(gender=gender, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/regional-qualifiers')
def api_regional_qualifiers():
    """Return regional qualifier list for a specific gender, year, and regional."""
    gender = request.args.get('gender', 'Boys').strip()
    regional_num = request.args.get('regional_num', type=int)
    year = request.args.get('year', default=2026, type=int)

    if regional_num is None:
        return jsonify({'error': 'regional_num is required'}), 400
    if year is None or year < 2000:
        return jsonify({'error': 'year must be a valid season year'}), 400

    try:
        payload = get_regional_qualifiers(gender=gender, regional_num=regional_num, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/state-qualifiers/status')
def api_state_qualifiers_status():
    """Return state readiness status for a gender and year."""
    gender = request.args.get('gender', 'Boys').strip()
    year = request.args.get('year', default=2026, type=int)
    if year is None or year < 2000:
        return jsonify({'error': 'year must be a valid season year'}), 400

    try:
        payload = get_state_qualifiers_status(gender=gender, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/state-qualifiers')
def api_state_qualifiers():
    """Return state qualifier list for a specific gender and year, using precomputed JSON if available."""
    gender = request.args.get('gender', 'Boys').strip().title()
    year = request.args.get('year', default=2026, type=int)
    if year is None or year < 2000:
        return jsonify({'error': 'year must be a valid season year'}), 400
    if gender not in ("Boys", "Girls"):
        return jsonify({'error': 'gender must be Boys or Girls'}), 400

    # Prefer precomputed JSON for speed
    precomputed_path = os.path.join(
        current_app.root_path,
        '..', 'frontend', 'static', 'data', 'state_predictions',
        f'state_qualifiers_{year}_{gender.lower()}.json',
    )
    if os.path.exists(precomputed_path):
        try:
            with open(precomputed_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            pass  # Fall through to live computation if file is unreadable

    # Fallback to live computation if file missing or unreadable
    try:
        payload = get_state_qualifiers(gender=gender, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/regional-qualifiers/top-list')
def api_regional_top_list():
    """Return combined, sorted event lists across all regionals (1-8) for a given gender/year.

    For each event, qualifiers from all 8 regionals are merged and sorted best-to-worst
    using result2 (lower is better for track events, higher for field events).
    """
    gender = (request.args.get('gender', 'Boys') or '').strip().title()
    year = request.args.get('year', default=2026, type=int)
    source = (request.args.get('source', 'rankings') or '').strip().lower()
    if source not in ('rankings', 'results'):
        return jsonify({'error': "source must be 'rankings' or 'results'"}), 400
    if year is None or year < 2000:
        return jsonify({'error': 'year must be a valid season year'}), 400
    if gender not in ('Boys', 'Girls'):
        return jsonify({'error': 'gender must be Boys or Girls'}), 400

    # Prefer precomputed JSON (much faster on production where SQLite I/O is slow).
    # rankings -> combined_rankings_*.json (sectional-based projection snapshot)
    # results  -> combined_results_*.json  (regional-based actuals)
    # Generated by web/backend/scripts/precompute_combined_rankings.py and
    # web/backend/scripts/precompute_combined_results.py respectively.
    file_prefix = 'combined_rankings' if source == 'rankings' else 'combined_results'
    precomputed_path = os.path.join(
        current_app.root_path,
        '..', 'frontend', 'static', 'data', 'regional_predictions',
        f'{file_prefix}_{year}_{gender.lower()}.json',
    )
    if os.path.exists(precomputed_path):
        try:
            with open(precomputed_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            # Fall through to live computation if the file is unreadable.
            pass

    # For source='results' we cannot fall back to the sectional-based live
    # computation (that would return projections, not actual regional results).
    # Return an empty payload so the UI shows "no data" instead of misleading data.
    if source == 'results':
        return jsonify({
            'context': {'gender': gender, 'year': year, 'source': 'results'},
            'events': [],
        })

    FIELD_EVENTS = {"High Jump", "Long Jump", "Triple Jump", "Shot Put", "Discus", "Pole Vault"}

    combined = {}
    event_meta = {}
    for regional_num in range(1, 9):
        try:
            payload = get_regional_qualifiers(gender=gender, regional_num=regional_num, year=year)
        except Exception:
            continue
        for event_block in payload.get('events', []):
            event_name = event_block.get('event')
            if not event_name:
                continue
            if event_name not in combined:
                combined[event_name] = []
                event_meta[event_name] = {
                    'event': event_name,
                    'event_type': event_block.get('event_type'),
                    'standard_mark': event_block.get('standard_mark'),
                }
            for row in event_block.get('qualifiers', []):
                if row.get('is_placeholder'):
                    continue
                enriched = dict(row)
                enriched['regional_num'] = regional_num
                combined[event_name].append(enriched)

    events_out = []
    for event_name, rows in combined.items():
        is_field = event_name in FIELD_EVENTS
        def sort_key(r, is_field=is_field):
            val = r.get('result2')
            if val is None:
                return float('-inf') if is_field else float('inf')
            return val
        sorted_rows = sorted(rows, key=sort_key, reverse=is_field)
        # De-duplicate: an athlete/school may appear multiple times across feeders; keep best result only
        seen = set()
        unique_rows = []
        for r in sorted_rows:
            key = (r.get('name') or r.get('school'), r.get('school'))
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(r)
        meta = event_meta[event_name]
        events_out.append({
            'event': event_name,
            'event_type': meta.get('event_type'),
            'standard_mark': meta.get('standard_mark'),
            'qualifiers': unique_rows,
        })

    return jsonify({
        'context': {'gender': gender, 'year': year},
        'events': events_out,
    })


# ---------------------------------------------------------------------------
# School dashboard v3 -- the only school dashboard API. The v2 page and its
# endpoints are gone; the get_school_dashboard_v2_* query functions they shared
# remain as the engine underneath, since v3 was built on them deliberately.
# ---------------------------------------------------------------------------

def _v3_season_status(gender, season):
    """Season completeness, with a switch for tests.

    The gate exists because qualifying cutoffs are read off a finished bracket, so
    a season still being run would produce confident-looking nonsense. That makes
    it far too strict for a fixture DB, which has one meet per round rather than
    32 -- hence the config flag, off only under test.
    """
    if not current_app.config.get('V3_REQUIRE_COMPLETE_SEASON', True):
        return {'complete': True, 'season': season}
    return get_school_dashboard_v3_season_status(gender, season)


def _v3_scope(school_id, gender, season):
    core = get_school_dashboard_v2_core(school_id, gender=gender, season=season)
    if not core:
        return None, None, None
    sel_gender = core['filters']['selected_gender']
    sel_season = core['filters']['selected_season']
    # Cutoffs are derived from the completed bracket, so a season still being run
    # would produce authoritative-looking nonsense. Refuse it here, once, rather
    # than in each endpoint.
    status = _v3_season_status(sel_gender, sel_season)
    if not status['complete']:
        raise ValueError(status['reason'])
    return core, sel_gender, sel_season


@api_bp.route('/v3/schools/<int:school_id>/dashboard/core')
def api_get_school_dashboard_v3_core(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        data = get_school_dashboard_v2_core(school_id, gender=gender, season=season)
        if not data:
            return jsonify({'error': 'not found'}), 404
        # Which seasons are finished, so the season control can mark the rest
        # unavailable instead of letting a click fail.
        sel_gender = data['filters']['selected_gender']
        incomplete = {}
        for value in data['filters'].get('seasons', []):
            if value == 'all-time':
                continue
            status = _v3_season_status(sel_gender, value)
            if not status['complete']:
                incomplete[str(value)] = status['reason']
        data = dict(data)
        data['filters'] = dict(data['filters'])
        data['filters']['incomplete_seasons'] = incomplete
        # Each stage against the same stage last season. It rides on core rather
        # than its own endpoint because the panel that needs it is already
        # rendered from core -- a second request would only add latency.
        sel_season = data['filters']['selected_season']
        if data.get('stage_results') and sel_season != 'all-time':
            data['stage_deltas'] = get_school_dashboard_v3_stage_deltas(
                school_id, sel_gender, int(sel_season))
        selected = data['filters']['selected_season']
        if str(selected) in incomplete:
            data['season_incomplete'] = incomplete[str(selected)]
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/scorecard')
def api_get_school_dashboard_v3_scorecard(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core, sel_gender, sel_season = _v3_scope(school_id, gender, season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        data = get_school_dashboard_v3_scorecard(school_id, sel_gender, sel_season)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/athletes')
def api_get_school_dashboard_v3_athletes(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core, sel_gender, sel_season = _v3_scope(school_id, gender, season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        data = get_school_dashboard_v3_athlete_scorecard(school_id, sel_gender, sel_season)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/ranking')
def api_get_school_dashboard_v3_ranking(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core, sel_gender, sel_season = _v3_scope(school_id, gender, season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        if sel_season == 'all-time':
            return jsonify({'error': 'ranking requires a specific postseason season'}), 400
        data = get_school_dashboard_v3_program_rank(school_id, sel_gender, int(sel_season))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/season-h2h')
def api_get_school_dashboard_v3_season_h2h(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core, sel_gender, sel_season = _v3_scope(school_id, gender, season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        data = get_school_dashboard_v3_season_h2h(school_id, sel_gender, sel_season)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/returning')
def api_get_school_dashboard_v3_returning(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core, sel_gender, sel_season = _v3_scope(school_id, gender, season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        data = get_school_dashboard_v3_returning(school_id, sel_gender, sel_season)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/leaderboard')
def api_get_school_dashboard_v3_leaderboard(school_id):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    # Absent or "all" means the whole field.
    top_n_arg = (request.args.get('top_n', '') or '').strip().lower()
    top_n = None
    if top_n_arg and top_n_arg != 'all':
        try:
            top_n = int(top_n_arg)
        except ValueError:
            return jsonify({'error': 'top_n must be all or an integer'}), 400
    enrollment_arg = (request.args.get('enrollment_max', '') or '').strip().lower()
    enrollment_max = None
    if enrollment_arg and enrollment_arg != 'all':
        try:
            enrollment_max = int(enrollment_arg)
        except ValueError:
            return jsonify({'error': 'enrollment_max must be all or an integer'}), 400

    try:
        core = get_school_dashboard_v2_core(school_id, gender=gender, season=season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        selected_season = core['filters']['selected_season']
        if selected_season == 'all-time':
            return jsonify({'error': 'leaderboard requires a specific postseason season'}), 400
        group = (request.args.get('group', '') or '').strip() or None
        data = get_school_dashboard_v2_leaderboard(
            school_id,
            core['filters']['selected_gender'],
            int(selected_season),
            top_n=top_n,
            enrollment_max=enrollment_max,
            group=group,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/event-rankings/<path:event_name>')
def api_get_school_dashboard_v3_event_rankings(school_id, event_name):
    """The statewide field for one event, which the table's rank column opens."""
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    # Same contract as the leaderboard: absent or "all" means the whole field.
    enrollment_arg = (request.args.get('enrollment_max', '') or '').strip().lower()
    enrollment_max = None
    if enrollment_arg and enrollment_arg != 'all':
        try:
            enrollment_max = int(enrollment_arg)
        except ValueError:
            return jsonify({'error': 'enrollment_max must be all or an integer'}), 400
    try:
        core = get_school_dashboard_v2_core(school_id, gender=gender, season=season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        data = get_school_dashboard_v3_event_rankings(
            school_id,
            core['filters']['selected_gender'],
            core['filters']['selected_season'],
            event_name,
            enrollment_max=enrollment_max,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


@api_bp.route('/v3/schools/<int:school_id>/dashboard/events/<path:event_name>')
def api_get_school_dashboard_v3_event_detail(school_id, event_name):
    gender = request.args.get('gender', CONST.GENDER.BOYS).strip()
    season = request.args.get('season')
    try:
        core = get_school_dashboard_v2_core(school_id, gender=gender, season=season)
        if not core:
            return jsonify({'error': 'not found'}), 404
        selected_season = core['filters']['selected_season']
        if selected_season == 'all-time':
            return jsonify({'error': 'event detail requires a specific postseason season'}), 400
        data = get_school_dashboard_v2_event_detail(
            school_id,
            core['filters']['selected_gender'],
            int(selected_season),
            event_name,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(data)


