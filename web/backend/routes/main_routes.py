from flask import render_template, request, url_for, Response
from . import main_bp
from ..queries import get_athletes
from ..models import Athlete, School
from sqlalchemy.orm import joinedload


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


@main_bp.route('/insights/reports/top-returning-athletes')
def top_returning_athletes_report_page():
    return render_template(
        'insights/report-viewer.html',
        title='Top Returning Athletes Report',
        description='A summary of the top returning Indiana high school track and field athletes.',
        pdf_url=url_for('static', filename='top_returning_athletes.pdf'),
        download_name='TrackInsights_Top_Returning_Athletes.pdf',
        show_credit_banner=True,
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
    school = School.query.get(school_id)
    return render_template(
        'school-dashboard.html',
        school_id=school_id,
        school_name=school.school_name if school else None,
        school_city=school.city if school else None,
    )


@main_bp.route('/athlete-dashboard/<int:athlete_id>')
def athlete_dashboard(athlete_id):
    athlete = Athlete.query.options(joinedload(Athlete.school)).get(athlete_id)
    return render_template(
        'athlete-dashboard.html',
        athlete_id=athlete_id,
        athlete_name=f"{athlete.first} {athlete.last}" if athlete else None,
        school_name=athlete.school.school_name if athlete and athlete.school else None,
    )


@main_bp.route('/athlete-dashboard/<int:athlete_id>/result/<int:meet_id>/<path:event_name>')
def athlete_result_detail(athlete_id, meet_id, event_name):
    result_type = request.args.get('result_type', 'Final')
    athlete = Athlete.query.options(joinedload(Athlete.school)).get(athlete_id)
    return render_template(
        'athlete-result-detail.html',
        athlete_id=athlete_id,
        meet_id=meet_id,
        event_name=event_name,
        result_type=result_type,
        athlete_name=f"{athlete.first} {athlete.last}" if athlete else None,
        school_name=athlete.school.school_name if athlete and athlete.school else None,
    )


@main_bp.route('/about')
def about():
    return render_template('about.html')


@main_bp.route('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /',
        '',
        f'Sitemap: {url_for("main.sitemap_xml", _external=True)}',
    ]
    return Response('\n'.join(lines), mimetype='text/plain')


@main_bp.route('/sitemap.xml')
def sitemap_xml():
    pages = [
        url_for('main.home', _external=True),
        url_for('main.search_page', _external=True),
        url_for('main.insights_page', _external=True),
        url_for('main.percentiles_report_page', _external=True),
        url_for('main.top_returning_athletes_report_page', _external=True),
        url_for('main.percentiles_query_page', _external=True),
        url_for('main.sectional_trends_page', _external=True),
        url_for('main.hypothetical_query_page', _external=True),
        url_for('main.about', _external=True),
    ]

    athletes = Athlete.query.with_entities(Athlete.athlete_id).all()
    for (aid,) in athletes:
        pages.append(url_for('main.athlete_dashboard', athlete_id=aid, _external=True))

    schools = School.query.with_entities(School.school_id).all()
    for (sid,) in schools:
        pages.append(url_for('main.school_dashboard', school_id=sid, _external=True))

    xml_entries = []
    for loc in pages:
        xml_entries.append(f'  <url><loc>{loc}</loc></url>')

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(xml_entries)
        + '\n</urlset>'
    )
    return Response(xml, mimetype='application/xml')


