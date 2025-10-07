from flask import render_template
from . import main_bp
from ..queries import get_athletes


@main_bp.route('/')
def home():
    athletes = get_athletes(20)
    return render_template('home.html', athletes=athletes)

