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
    return render_template('queries.html')


@main_bp.route('/queries/percentiles')
def percentiles_query_page():
    return render_template('queries-percentiles.html')


@main_bp.route('/queries/sectional-trends')
def sectional_trends_page():
    return render_template('queries-sectional-trends.html')


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


