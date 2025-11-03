from flask import jsonify, request
from . import api_bp
from ..queries import (
    get_athletes,
    get_athlete_by_id,
    add_athlete,
    search_bar,
    get_athlete_dashboard_data,
    get_athlete_result_rankings,
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

