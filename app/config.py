import os
import re

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database: use DATABASE_URL from env (Render sets this for PostgreSQL),
    # fall back to local SQLite for development.
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url:
        # Render uses postgres:// but SQLAlchemy 1.4+ needs postgresql://
        _db_url = re.sub(r'^postgres://', 'postgresql://', _db_url)
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
            BASE_DIR, '..', 'instance', 'app.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(BASE_DIR, '..', 'uploads')
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {'py', 'java', 'c', 'cpp', 'js', 'txt', 'md', 'docx', 'pdf'}
    SIMILARITY_THRESHOLD_DEFAULT = 0.70
    CODE_LANGUAGES = {'python', 'java', 'c', 'cpp', 'javascript'}
    TEXT_LANGUAGES = {'txt', 'md', 'docx', 'pdf'}
