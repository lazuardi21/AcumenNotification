"""
Notification Service — Celery application configuration.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Create Celery app
celery = Celery(
    'notification_service',
    broker=os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672//'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Retry configuration
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Task routing
    task_routes={
        'tasks.process_event': {'queue': 'events'},
        'tasks.send_notification_task': {'queue': 'notifications'},
        'tasks.retry_failed_task': {'queue': 'maintenance'},
    },

    # Periodic tasks (Celery Beat)
    beat_schedule={
        'retry-failed-notifications': {
            'task': 'tasks.retry_failed_task',
            'schedule': 300.0,  # Every 5 minutes
        },
        'send-pending-notifications': {
            'task': 'tasks.send_pending_task',
            'schedule': 10.0,  # Every 10 seconds
        },
    },
)


def init_celery(app):
    """Initialize Celery with Flask app context."""
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
