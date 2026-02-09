from flask import render_template, request
from . import main_bp
from ..queries import get_athletes


@main_bp.route('/')
def home():
    return render_template('home.html')


@main_bp.route('/search')
def search_page():
    return render_template('athlete-search.html')


@main_bp.route('/queries')
def queries_page():
    return render_template('queries/index.html')


@main_bp.route('/queries/percentiles')
def percentiles_query_page():
    return render_template('queries/percentiles.html')


@main_bp.route('/queries/sectional-trends')
def sectional_trends_page():
    return render_template('queries/sectional-trends.html')


@main_bp.route('/queries/hypothetical')
def hypothetical_query_page():
    return render_template('queries/hypothetical.html')


@main_bp.route('/queries/hypothetical/result')
def hypothetical_result_detail():
    event = request.args.get('event', '')
    time = request.args.get('time', '')
    gender = request.args.get('gender', '')
    year = request.args.get('year', '')
    meet_type = request.args.get('meet_type', 'Sectional')
    enrollment = request.args.get('enrollment', '')
    grade_level = request.args.get('grade_level', '')
    return render_template(
        'queries/hypothetical-result-detail.html',
        event_name=event,
        time_input=time,
        gender=gender,
        year=year,
        meet_type=meet_type,
        enrollment=enrollment,
        grade_level=grade_level,
    )


@main_bp.route('/athlete-dashboard/<int:athlete_id>')
def athlete_dashboard(athlete_id):
    return render_template('athlete-dashboard.html', athlete_id=athlete_id)


@main_bp.route('/athlete-dashboard/<int:athlete_id>/result/<int:meet_id>/<path:event_name>')
def athlete_result_detail(athlete_id, meet_id, event_name):
    result_type = request.args.get('result_type', 'Final')
    return render_template(
        'athlete-result-detail.html',
        athlete_id=athlete_id,
        meet_id=meet_id,
        event_name=event_name,
        result_type=result_type,
    )


@main_bp.route('/about')
def about():
    return render_template('about.html')


