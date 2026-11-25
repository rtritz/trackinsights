import os

from flask import jsonify, request, current_app
from . import api_bp
from common import cache_db
from ..queries import (
    current_season,
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
    get_regional_qualifiers_status,
    get_regional_qualifiers,
    get_state_qualifiers_status,
    get_state_qualifiers,
)


def _serve_precomputed(name):
    """Send a stored artifact's JSON to the browser as is, or None if not built.

    The stored JSON IS the response -- these routes return the whole artifact --
    so it is sent without parsing and re-serializing (12ms on the largest).
    Returning None lets the caller fall through to live computation.
    """
    data = cache_db.artifact_json(name)
    if not data:
        return None
    return current_app.response_class(data, mimetype='application/json')


# ---------------------------------------------------------------------------
# Qualifier pages. They show only the current season -- the newest year with
# results in Track.db -- so a `year` in the request is ignored.
# ---------------------------------------------------------------------------

def _qualifier_request():
    """(gender, year) for a qualifier API request, or an error response."""
    gender = (request.args.get('gender', 'Boys') or '').strip().title()
    if gender not in ('Boys', 'Girls'):
        return None, None, (jsonify({'error': 'gender must be Boys or Girls'}), 400)
    year = current_season()
    if year is None:
        return None, None, (jsonify({'error': 'No results have been loaded yet.'}), 404)
    return gender, year, None


_REGIONAL_MEMO = {}


def _stored_regional_qualifiers(gender, year):
    """The stored status and 8 regional lists (precompute_regional_qualifiers),
    decoded once per cache build; None when not built."""
    name = 'regional_qualifiers_%d_%s' % (year, gender.lower())
    try:
        version = os.path.getmtime(cache_db.CACHE_DB_PATH)
    except OSError:
        return None
    key = (name, version)
    if key not in _REGIONAL_MEMO:
        _REGIONAL_MEMO.clear()  # one build's worth at a time
        payload = cache_db.load_artifact(name)
        _REGIONAL_MEMO[key] = payload if isinstance(payload, dict) else None
    return _REGIONAL_MEMO[key]


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


@api_bp.route('/regional-qualifiers/status')
def api_regional_qualifiers_status():
    """Return regional readiness status for a gender, current season."""
    gender, year, error = _qualifier_request()
    if error:
        return error
    stored = _stored_regional_qualifiers(gender, year)
    if stored and isinstance(stored.get('status'), dict):
        return jsonify(stored['status'])

    try:
        payload = get_regional_qualifiers_status(gender=gender, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/regional-qualifiers')
def api_regional_qualifiers():
    """Return regional qualifier list for a gender and regional, current season."""
    regional_num = request.args.get('regional_num', type=int)
    if regional_num is None:
        return jsonify({'error': 'regional_num is required'}), 400
    gender, year, error = _qualifier_request()
    if error:
        return error
    stored = _stored_regional_qualifiers(gender, year)
    regional = ((stored or {}).get('regionals') or {}).get(str(regional_num))
    if isinstance(regional, dict):
        return jsonify(regional)

    try:
        payload = get_regional_qualifiers(gender=gender, regional_num=regional_num, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/state-qualifiers/status')
def api_state_qualifiers_status():
    """Return state readiness status for a gender, current season."""
    gender, year, error = _qualifier_request()
    if error:
        return error

    try:
        payload = get_state_qualifiers_status(gender=gender, year=year)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/state-qualifiers')
def api_state_qualifiers():
    """Return state qualifier list for a gender, current season, from the stored data if built."""
    gender, year, error = _qualifier_request()
    if error:
        return error

    # Prefer the precomputed list for speed
    served = _serve_precomputed(f'state_qualifiers_{year}_{gender.lower()}')
    if served is not None:
        return served

    # Fall back to live computation if it has not been built
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
    source = (request.args.get('source', 'rankings') or '').strip().lower()
    if source not in ('rankings', 'results'):
        return jsonify({'error': "source must be 'rankings' or 'results'"}), 400
    gender, year, error = _qualifier_request()
    if error:
        return error

    # Prefer the precomputed lists (much faster on production where SQLite I/O is slow).
    # rankings -> combined_rankings_* (sectional-based projection snapshot)
    # results  -> combined_results_*  (regional-based actuals)
    # Generated by web/app/jobs/precompute_combined_rankings.py and
    # web/app/jobs/precompute_combined_results.py respectively.
    file_prefix = 'combined_rankings' if source == 'rankings' else 'combined_results'
    served = _serve_precomputed(f'{file_prefix}_{year}_{gender.lower()}')
    if served is not None:
        return served

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
# School page: the ranked lists behind a rank (the rank popups).
#
# Fetched only when a reader opens one, because they are large and shared -- the
# statewide table alone is 394 rows, identical for every school, so it is stored
# once per gender/season rather than embedded in each school's page.
# ---------------------------------------------------------------------------
@api_bp.route('/rankings/<gender>/<season>')
def api_rankings(gender, season):
    event = (request.args.get('event') or '').strip()
    if season == 'all-time':
        # Every athlete's best across all seasons -- the list behind an All-Time rank.
        from ..services.school_page import all_time_rankings
        payload = all_time_rankings(gender, event)
    else:
        payload = cache_db.load_rankings(gender, season, event)
    if payload is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(payload)
