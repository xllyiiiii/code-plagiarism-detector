from flask import Blueprint, render_template

viz_bp = Blueprint('visualization', __name__)


@viz_bp.route('/')
def index():
    return render_template('visualization/index.html')
