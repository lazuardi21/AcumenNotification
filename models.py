"""
Notification Service — SQLAlchemy Models.
"""
import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Notification(db.Model):
    """A notification created for a user based on portfolio events and rules."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)  # transaction_alert, threshold_alert, daily_summary
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(20), default='email')  # email, sms, push
    status = db.Column(db.String(20), default='pending', index=True)  # pending, sent, failed
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    metadata_json = db.Column(db.JSON, default=dict)  # Extra event context
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type,
            'title': self.title,
            'message': self.message,
            'channel': self.channel,
            'status': self.status,
            'retry_count': self.retry_count,
            'metadata': self.metadata_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }


class UserPreference(db.Model):
    """User notification preferences."""
    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    email_enabled = db.Column(db.Boolean, default=True)
    sms_enabled = db.Column(db.Boolean, default=False)
    push_enabled = db.Column(db.Boolean, default=True)
    quiet_hours_start = db.Column(db.String(5), nullable=True)  # HH:MM format
    quiet_hours_end = db.Column(db.String(5), nullable=True)    # HH:MM format
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'email_enabled': self.email_enabled,
            'sms_enabled': self.sms_enabled,
            'push_enabled': self.push_enabled,
            'quiet_hours_start': self.quiet_hours_start,
            'quiet_hours_end': self.quiet_hours_end,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationRule(db.Model):
    """User-defined notification trigger rules."""
    __tablename__ = 'notification_rules'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)  # threshold, transaction, daily_summary
    conditions = db.Column(db.JSON, nullable=False)
    # Example conditions:
    #   threshold: {"field": "total_amount", "operator": ">", "value": 10000}
    #   transaction: {"types": ["BUY", "SELL"], "tickers": ["AAPL", "GOOGL"]}
    #   daily_summary: {"time": "18:00"}
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'rule_type': self.rule_type,
            'conditions': self.conditions,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ProcessedEvent(db.Model):
    """Track processed events for idempotency."""
    __tablename__ = 'processed_events'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    processed_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
