# app/__init__.py

from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before Config: class-level settings are read at import time.
_backend_root = Path(__file__).resolve().parent.parent
load_dotenv(_backend_root / ".env", override=True)

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_migrate import Migrate
from .config import Config

# Unset empty env vars so config defaults apply
for _key in ("SECRET_KEY", "JWT_SECRET_KEY"):
    if os.getenv(_key) == "":
        os.environ.pop(_key, None)

db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(
        app,
        supports_credentials=True,
        resources={r"/*": {"origins": app.config.get("CORS_ORIGINS", ["*"])}},
        expose_headers=["Authorization"],
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    )
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    # Import models so Flask-Migrate sees them
    from . import models  # noqa: F401

    from .routes import register_blueprints
    register_blueprints(app)

    from .commands import register_commands
    register_commands(app)

    return app
