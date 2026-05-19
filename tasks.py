"""
Notification Service — Celery task definitions.

All tasks use the Flask app context via the ContextTask base class
configured in celery_app.py, so they can access the database and services.
"""
import os
import sys
import logging

# Ensure /app is on the Python path for forked worker processes
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from celery_app import celery

logger = logging.getLogger(__name__)

# Eagerly create the Flask app so all workers share a single instance
_flask_app = None


def _get_app():
    """Get or create the Flask application (singleton)."""
    global _flask_app
    if _flask_app is None:
        from app import create_app
        _flask_app = create_app()
    return _flask_app


@celery.task(bind=True, name='tasks.process_event', max_retries=3,
             default_retry_delay=10, acks_late=True)
def process_event(self, event_id, event_type, event_data):
    """Process a portfolio event — evaluate rules and create notifications.

    Called by the RabbitMQ consumer when a portfolio event arrives.
    """
    try:
        app = _get_app()
        with app.app_context():
            from services import process_portfolio_event
            notification_ids = process_portfolio_event(event_id, event_type, event_data)
            logger.info(f"Event processed: {event_id} → {len(notification_ids)} notifications")

            # Queue delivery for each notification
            for nid in notification_ids:
                send_notification_task.delay(nid)

            return {'event_id': event_id, 'notifications_created': len(notification_ids)}

    except Exception as e:
        logger.error(f"Failed to process event {event_id}: {e}", exc_info=True)
        raise self.retry(exc=e)


@celery.task(bind=True, name='tasks.send_notification_task', max_retries=3,
             default_retry_delay=15, acks_late=True)
def send_notification_task(self, notification_id):
    """Send a single notification via its configured channel."""
    try:
        app = _get_app()
        with app.app_context():
            from services import send_notification
            success = send_notification(notification_id)
            return {'notification_id': notification_id, 'success': success}

    except Exception as e:
        logger.error(f"Failed to send notification {notification_id}: {e}", exc_info=True)
        raise self.retry(exc=e)


@celery.task(name='tasks.retry_failed_task')
def retry_failed_task():
    """Periodic task to retry failed notifications."""
    try:
        app = _get_app()
        with app.app_context():
            from services import retry_failed_notifications
            count = retry_failed_notifications()
            if count:
                logger.info(f"Reset {count} failed notifications for retry")
            return {'retried': count}

    except Exception as e:
        logger.error(f"Retry failed task error: {e}", exc_info=True)


@celery.task(name='tasks.send_pending_task')
def send_pending_task():
    """Periodic task to send pending notifications."""
    try:
        app = _get_app()
        with app.app_context():
            from models import Notification
            pending = Notification.query.filter_by(status='pending').limit(50).all()
            for notification in pending:
                send_notification_task.delay(notification.id)
            return {'queued': len(pending)}

    except Exception as e:
        logger.error(f"Send pending task error: {e}", exc_info=True)
