from flask import jsonify, request
from . import api_bp
from ..queries import get_athletes, get_athlete_by_id, add_athlete, search_bar


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
        'school': a.school.school_name if a.school else None
    })


@api_bp.route('/athletes', methods=['POST'])
def api_add_athlete():
    data = request.get_json() or {}
    fn = data.get('first_name')
    ln = data.get('last_name')
    if not fn or not ln:
        return jsonify({'error': 'first_name and last_name required'}), 400
    a = add_athlete(fn, ln, school=data.get('school'))
    return jsonify({'id': a.athlete_id}), 201


@api_bp.route('/search')
def api_search_bar():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    results = search_bar(query)
    return jsonify(results)

