from flask import render_template, request, url_for
from . import main_bp
from ..queries import get_athletes


@main_bp.route('/')
def home():
    return render_template('home.html')


@main_bp.route('/search')
def search_page():
    return render_template('athlete-search.html')


@main_bp.route('/insights')
def insights_page():
    return render_template('insights/index.html')


@main_bp.route('/insights/reports/percentiles-summary')
def percentiles_report_page():
    return render_template(
        'insights/report-viewer.html',
        title='Percentiles Summary Report',
        description='A comprehensive overview of track & field percentiles across all events, genders, and meet types.',
        pdf_url=url_for('static', filename='percentiles_by10_readable.pdf'),
        download_name='TrackInsights_Percentiles_Summary.pdf',
    )


@main_bp.route('/insights/percentiles')
def percentiles_query_page():
    return render_template('insights/percentiles.html')


@main_bp.route('/insights/sectional-trends')
def sectional_trends_page():
    return render_template('insights/sectional-trends.html')


@main_bp.route('/insights/hypothetical')
def hypothetical_query_page():
    return render_template('insights/hypothetical.html')


@main_bp.route('/insights/hypothetical/result')
def hypothetical_result_detail():
    event = request.args.get('event', '')
    time = request.args.get('time', '')
    gender = request.args.get('gender', '')
    year = request.args.get('year', '')
    meet_type = request.args.get('meet_type', 'Sectional')
    enrollment = request.args.get('enrollment', '')
    grade_level = request.args.get('grade_level', '')
    return render_template(
        'insights/hypothetical-result-detail.html',
        event_name=event,
        time_input=time,
        gender=gender,
        year=year,
        meet_type=meet_type,
        enrollment=enrollment,
        grade_level=grade_level,
    )


@main_bp.route('/school-dashboard/<int:school_id>')
def school_dashboard(school_id):
    return render_template('school-dashboard.html', school_id=school_id)


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


