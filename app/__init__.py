import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录后再访问此页面。'


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    from app.config import Config
    app.config.from_object(Config)
    if config:
        app.config.from_mapping(config)

    # Ensure instance folder and upload folder exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from flask import redirect, url_for

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    from app.auth.routes import auth_bp
    from app.courses.routes import courses_bp
    from app.assignments.routes import assignments_bp
    from app.plagiarism.routes import plagiarism_bp
    from app.visualization.routes import viz_bp
    from app.admin.routes import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(courses_bp, url_prefix='/courses')
    app.register_blueprint(assignments_bp, url_prefix='/assignments')
    app.register_blueprint(plagiarism_bp, url_prefix='/plagiarism')
    app.register_blueprint(viz_bp, url_prefix='/viz')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    with app.app_context():
        db.create_all()

    return app
