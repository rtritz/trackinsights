from flask import Blueprint

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

from . import main_routes, api_routes  # noqa: F401
