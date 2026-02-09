from flask import jsonify, request
from . import api_bp
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

