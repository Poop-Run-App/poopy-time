from .health_routes import health_bp
from .auth_routes import auth_bp
from .bathroom_routes import bathroom_bp


def register_blueprints(app):
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(bathroom_bp, url_prefix="/bathrooms")
