from flask import render_template
from . import main_bp
from ..queries import get_athletes


@main_bp.route('/')
def home():
    athletes = get_athletes(20)
    return render_template('home.html', athletes=athletes)


@main_bp.route('/search')
def search_page():
    return render_template('athlete-search.html')


@main_bp.route('/dashboard-test')
def dashboard_test_page():
    return render_template('dashboard-test.html')

