from datetime import datetime

from flask import render_template, request, url_for, Response
from . import main_bp
from ..queries import current_season, get_athletes
from ..models import Athlete, School
from ..videos import INTERVIEW_VIDEOS
from common import cache_db
from common.regional_hosts import get_configured_regional_hosts
from sqlalchemy.orm import joinedload

from ..analytics.regional_predictions import get_regional_predictions

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
        pdf_url=url_for('static', filename='reports/percentiles_by10_readable.pdf'),
        download_name='TrackInsights_Percentiles_Summary.pdf',
    )


@main_bp.route('/insights/reports/top-returning-athletes')
def top_returning_athletes_report_page():
    return render_template(
        'insights/report-viewer.html',
        title='Top Returning Athletes Report',
        description='A summary of the top returning Indiana high school track and field athletes.',
        pdf_url=url_for('static', filename='reports/top_returning_athletes.pdf'),
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


# The report pages read their data from dashboard_cache.db (common/cache_db.py),
# built by build_all. A report whose data has not been built shows its "not
# available" state rather than an error.
def _updated_label():
    return '%s %d, %d' % (datetime.now().strftime('%B'), datetime.now().day,
                          datetime.now().year)


@main_bp.route('/insights/reports/2026-regional-predictions')
def regional_predictions_2026_report_page():
    year = 2026
    top_n = 10
    predictions_girls = cache_db.load_artifact(f'regional_predictions_{year}_girls', [])
    predictions_boys = cache_db.load_artifact(f'regional_predictions_{year}_boys', [])
    updated_label = _updated_label()

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


@main_bp.route('/insights/reports/2026-state-predictions')
def state_predictions_2026_report_page():
    year = 2026
    not_built = {"ready": False, "rows": [], "missing_regionals": [], "regionals_loaded": 0}
    girls = cache_db.load_artifact(f'state_predictions_{year}_girls', dict(not_built))
    boys = cache_db.load_artifact(f'state_predictions_{year}_boys', dict(not_built))
    updated_label = _updated_label()

    girls_unavailable = not girls.get('ready') or not girls.get('rows')
    boys_unavailable = not boys.get('ready') or not boys.get('rows')

    return render_template(
        'insights/2026-state-predictions.html',
        year=year,
        girls=girls,
        boys=boys,
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
        page_subtitle="Unofficial lists — scratches made at Sectionals aren't reflected.",
        coverage_unit='sectionals',
        completed_field='completed_sectionals',
        total_field='total_sectionals',
        missing_field='missing_sectionals',
        load_error='Unable to load regional qualifiers.',
        detail_unavailable_text='That regional is awaiting meet result data.',
        api_status_url='/api/regional-qualifiers/status',
        api_detail_url='/api/regional-qualifiers',
        current_year=current_season(),
    )


@main_bp.route('/insights/state-qualifiers')
def state_qualifiers_page():
    return render_template(
        'insights/state-qualifiers.html',
        page_heading='Unofficial State Qualifiers',
        page_title='Unofficial State Qualifiers - Track Insights',
        page_description='Unofficial state qualifier lists.',
        page_subtitle="Unofficial lists — scratches made at Regionals aren't reflected.",
        coverage_unit='regional meet results',
        completed_field='completed_regionals',
        total_field='total_regionals',
        missing_field='missing_regionals',
        load_error='Unable to load state qualifiers.',
        status_error='Unable to load state status.',
        pending_text='State qualifiers are pending.',
        api_status_url='/api/state-qualifiers/status',
        api_detail_url='/api/state-qualifiers',
        current_year=current_season(),
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
@main_bp.route('/school-dashboard/<int:school_id>/<gender>/<season>')
def school_dashboard(school_id, gender=None, season=None):
    from flask import abort
    from ..services.school_page import page_html

    def render(payload, charts):
        return render_template('school-page.html', payload=payload, school_id=school_id,
                               chart_events=charts)

    try:
        # The finished page, cached (compressed) until Track.db or the rankings
        # cache changes; see page_html.
        html = page_html(school_id, gender, season, render)
    except ValueError:
        abort(400)
    if html is None:
        abort(404)
    return html


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

