import os
from datetime import timedelta


class Config:
    # Database — SQLite locally, PostgreSQL in production
    DATABASE_URL = os.getenv('DATABASE_URL') or None
    DB_USERNAME = os.getenv('DB_USERNAME') or None
    DB_PASSWORD = os.getenv('DB_PASSWORD') or None
    DB_HOST = os.getenv('DB_HOST') or None
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'postgres')

    # Priority:
    # 1) USE_LOCAL_SQLITE  2) DATABASE_URL  3) DB_* credentials  4) SQLite fallback
    _use_local_sqlite = os.getenv("USE_LOCAL_SQLITE", "").lower() in ("1", "true", "yes")
    if _use_local_sqlite:
        SQLALCHEMY_DATABASE_URI = "sqlite:///../instance/app.db"
    elif DATABASE_URL and DATABASE_URL.strip():
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    elif DB_USERNAME and DB_PASSWORD and DB_HOST and DB_HOST.strip():
        SQLALCHEMY_DATABASE_URI = f'postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///../instance/app.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Secrets (dev defaults — set real values in production)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-me-in-production-0000'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'dev-jwt-secret-key-change-me-in-production-0000'
    jwt_hours = os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(jwt_hours)) if jwt_hours and jwt_hours.isdigit() else timedelta(hours=24)

    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    # CORS
    CORS_ORIGINS = os.getenv('CORS_ORIGINS').split(',') if os.getenv('CORS_ORIGINS') else ['*']
