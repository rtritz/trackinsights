from flask import render_template
from . import main_bp
from ..queries import get_athletes


@main_bp.route('/')
def home():
    athletes = get_athletes(20)
    return render_template('home.html', athletes=athletes)

@main_bp.route('/home2')
def home2():
    athletes = get_athletes(20)
    return render_template('home2.html', athletes=athletes)

@main_bp.route('/home3')
def home3():
    athletes = get_athletes(20)
    return render_template('home3.html', athletes=athletes)

@main_bp.route('/home4')
def home4():
    athletes = get_athletes(20)
    return render_template('home4.html', athletes=athletes)

@main_bp.route('/search')
def search_page():
    return render_template('athlete-search.html')


@main_bp.route('/athlete-dashboard/<int:athlete_id>')
def athlete_dashboard(athlete_id):
    return render_template('athlete-dashboard.html', athlete_id=athlete_id)


@main_bp.route('/about')
def about():
    return render_template('about.html')


