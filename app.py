"""
Notification Service — Flask application factory.
"""
import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from flask_caching import Cache

from models import db
from config import config_map
from shared.auth import init_auth
from shared.tracing import init_tracing
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)

cache = Cache()
migrate = Migrate()

_app_instance = None


def create_app(config_name=None):
    """Application factory for Notification Service."""
    global _app_instance

    # Return cached instance for Celery workers
    if _app_instance is not None:
        return _app_instance

    # Setup structured logging
    setup_logging()

    config_name = config_name or os.environ.get('FLASK_ENV', 'production')
    cfg = config_map.get(config_name, config_map['production'])

    app = Flask(__name__)
    app.config.from_object(cfg)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize auth
    init_auth(
        secret=app.config['SECRET_KEY'],
        algorithm=app.config.get('JWT_ALGORITHM', 'HS256'),
        expiry_hours=app.config.get('JWT_EXPIRY_HOURS', 24),
    )

    # Initialize distributed tracing
    init_tracing(app, service_name='notification-service')

    # Initialize Celery
    from celery_app import init_celery
    init_celery(app)

    # Register blueprints
    from routes import notification_bp, preference_bp, rule_bp
    app.register_blueprint(notification_bp)
    app.register_blueprint(preference_bp)
    app.register_blueprint(rule_bp)

    # Health check
    @app.route('/health', methods=['GET'])
    def health():
        health_status = {'status': 'healthy', 'service': 'notification-service'}
        try:
            db.session.execute(db.text('SELECT 1'))
            health_status['database'] = 'connected'
        except Exception as e:
            health_status['database'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'
        return jsonify(health_status)

    # Global error handlers
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({'error': 'Bad request', 'message': str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

    # Create tables
    with app.app_context():
        db.create_all()
        logger.info("Database tables created/verified")

    _app_instance = app
    logger.info(f"Notification Service started (config={config_name})")
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5002, debug=True)
