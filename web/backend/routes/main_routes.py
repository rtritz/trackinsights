from datetime import datetime

from flask import render_template, request, url_for, Response
from . import main_bp
from ..queries import get_athletes
from ..models import Athlete, School
from ..videos import INTERVIEW_VIDEOS
from ..util.regional_hosts import get_configured_regional_hosts
from sqlalchemy.orm import joinedload

# regional_predictions lives under backend/scripts; queries.py already adds
# that directory to sys.path, so this import resolves at app boot.
from regional_predictions import get_regional_predictions  # type: ignore  # noqa: E402

# Master switch for the 2025 accuracy-check report. When False, the card on the
# /insights page is hidden and the URL returns a 404. Flip to False before
# pushing public; flip to True locally to spot-check the model.
SHOW_2025_REGIONAL_PREDICTIONS = True


@main_bp.route('/')
def home():
    return render_template('home.html')


@main_bp.route('/search')
def search_page():
    return render_template('athlete-search.html')


@main_bp.route('/insights')
def insights_page():
    return render_template(
        'insights/index.html',
        show_2025_regional_predictions=SHOW_2025_REGIONAL_PREDICTIONS,
    )


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


# Register the 2026 regional predictions report route
@main_bp.route('/insights/reports/2026-regional-predictions')
def regional_predictions_2026_report_page():
    import os, json
    from datetime import datetime
    year = 2026
    top_n = 10
    static_dir = os.path.join(os.path.dirname(__file__), '../../frontend/static/data/regional_predictions')
    girls_path = os.path.join(static_dir, f'regional_predictions_{year}_girls.json')
    boys_path = os.path.join(static_dir, f'regional_predictions_{year}_boys.json')
    try:
        with open(girls_path, encoding='utf-8') as f:
            predictions_girls = json.load(f)
    except Exception:
        predictions_girls = []
    try:
        with open(boys_path, encoding='utf-8') as f:
            predictions_boys = json.load(f)
    except Exception:
        predictions_boys = []
    now = datetime.now()
    updated_label = f"{now.strftime('%B')} {now.day}, {now.year}"

    girls_unavailable = not any(r.get('rows') for r in predictions_girls)
    boys_unavailable = not any(r.get('rows') for r in predictions_boys)

    return render_template(
        'insights/2026-regional-predictions.html',
        year=year,
        top_n=top_n,
        predictions_girls=predictions_girls,
        predictions_boys=predictions_boys,
        girls_unavailable=girls_unavailable,
        boys_unavailable=boys_unavailable,
        updated_label=updated_label,
    )


@main_bp.route('/insights/reports/2025-regional-predictions')
def regional_predictions_2025_report_page():
    if not SHOW_2025_REGIONAL_PREDICTIONS:
        from flask import abort
        abort(404)
    year = 2025
    top_n = 10
    sections = []
    for gender in ('Boys', 'Girls'):
        hosts = get_configured_regional_hosts(year, gender)
        predictions = get_regional_predictions(year, gender, top_n=top_n, hosts=hosts)
        sections.append({'gender': gender, 'predictions': predictions})
    return render_template(
        'insights/2025-regional-predictions.html',
        year=year,
        top_n=top_n,
        sections=sections,
    )


@main_bp.route('/insights/regional-qualifiers')
def regional_qualifiers_page():
    return render_template(
        'insights/regional-qualifiers.html',
        page_heading='Unofficial Regional Qualifiers',
        page_title='Unofficial Regional Qualifiers - Track Insights',
        page_description='Unofficial regional qualifier lists.',
        page_subtitle='These lists are unofficial and do not reflect any scratches that may have been made at the sectional level.',
        coverage_unit='sectionals',
        completed_field='completed_sectionals',
        total_field='total_sectionals',
        missing_field='missing_sectionals',
        load_error='Unable to load regional qualifiers.',
        detail_unavailable_text='That regional is awaiting meet result data.',
        api_status_url='/api/regional-qualifiers/status',
        api_detail_url='/api/regional-qualifiers',
    )


@main_bp.route('/insights/state-qualifiers')
def state_qualifiers_page():
    return render_template(
        'insights/state-qualifiers.html',
        page_heading='Unofficial State Qualifiers',
        page_title='Unofficial State Qualifiers - Track Insights',
        page_description='Unofficial state qualifier lists.',
        page_subtitle='These lists are unofficial and do not reflect any scratches that may have been made at the regional level.',
        coverage_unit='regional meet results',
        completed_field='completed_regionals',
        total_field='total_regionals',
        missing_field='missing_regionals',
        load_error='Unable to load state qualifiers.',
        status_error='Unable to load state status.',
        pending_text='State qualifiers are pending.',
        api_status_url='/api/state-qualifiers/status',
        api_detail_url='/api/state-qualifiers',
    )


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


@main_bp.route('/interviews')
def interviews_page():
    return render_template('interviews.html', videos=INTERVIEW_VIDEOS)


@main_bp.route('/athlete-dashboard/<int:athlete_id>')
def athlete_dashboard(athlete_id):
    athlete = Athlete.query.options(joinedload(Athlete.school)).get(athlete_id)
    athlete_id_key = str(athlete_id)
    athlete_videos = [
        video for video in INTERVIEW_VIDEOS
        if video.get('athlete_id') is not None and str(video.get('athlete_id')).strip() == athlete_id_key
    ]

    return render_template(
        'athlete-dashboard.html',
        athlete_id=athlete_id,
        athlete_name=f"{athlete.first} {athlete.last}" if athlete else None,
        school_name=athlete.school.school_name if athlete and athlete.school else None,
        athlete_videos=athlete_videos,
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
        url_for('main.regional_predictions_2026_report_page', _external=True),
        url_for('main.percentiles_query_page', _external=True),
        url_for('main.sectional_trends_page', _external=True),
        url_for('main.hypothetical_query_page', _external=True),
        url_for('main.regional_qualifiers_page', _external=True),
        url_for('main.state_qualifiers_page', _external=True),
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


