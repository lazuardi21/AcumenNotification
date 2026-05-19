"""
Notification Service — Business logic layer.
"""
import logging
import datetime
from models import db, Notification, UserPreference, NotificationRule, ProcessedEvent
from rule_engine import evaluate_rules, generate_notification_content

logger = logging.getLogger(__name__)


# =============================================================================
# Event Processing
# =============================================================================

def process_portfolio_event(event_id, event_type, event_data):
    """Process an incoming portfolio event.

    1. Check idempotency (skip if already processed)
    2. Load user's notification rules
    3. Evaluate rules against event
    4. Create notifications for matching rules
    5. Mark event as processed

    Returns:
        list: Created notification IDs
    """
    # Idempotency check
    if ProcessedEvent.query.filter_by(event_id=event_id).first():
        logger.info(f"Event already processed (idempotent skip): {event_id}")
        return []

    user_id = event_data.get('user_id')
    if not user_id:
        logger.warning(f"Event missing user_id: {event_id}")
        return []

    # Load active rules for this user
    rules = NotificationRule.query.filter_by(user_id=user_id, is_active=True).all()
    if not rules:
        logger.info(f"No active rules for user {user_id}")
        _mark_event_processed(event_id, event_type)
        return []

    # Evaluate rules
    matching_rules = evaluate_rules(rules, event_data)

    # Load user preferences
    preferences = UserPreference.query.filter_by(user_id=user_id).first()

    # Create notifications for each matching rule
    created_ids = []
    for rule in matching_rules:
        title, message, notif_type = generate_notification_content(rule, event_data)
        channels = _get_channels(preferences)

        for channel in channels:
            notification = Notification(
                user_id=user_id,
                type=notif_type,
                title=title,
                message=message,
                channel=channel,
                status='pending',
                metadata_json={
                    'event_id': event_id,
                    'event_type': event_type,
                    'rule_id': rule.id,
                    'rule_name': rule.name,
                    'transaction': event_data.get('transaction', {}),
                },
            )
            db.session.add(notification)
            db.session.flush()
            created_ids.append(notification.id)

    # Mark event as processed
    _mark_event_processed(event_id, event_type)

    db.session.commit()
    logger.info(f"Processed event {event_id}: {len(created_ids)} notifications created")
    return created_ids


def _mark_event_processed(event_id, event_type):
    """Record that an event has been processed (for idempotency)."""
    processed = ProcessedEvent(event_id=event_id, event_type=event_type)
    db.session.add(processed)


def _get_channels(preferences):
    """Get enabled notification channels based on user preferences."""
    if not preferences:
        return ['email']  # Default

    channels = []
    if preferences.email_enabled:
        channels.append('email')
    if preferences.sms_enabled:
        channels.append('sms')
    if preferences.push_enabled:
        channels.append('push')
    return channels or ['email']


# =============================================================================
# Notification Delivery (Mock)
# =============================================================================

def send_notification(notification_id):
    """Send a notification via its configured channel (mock implementation).

    In production, this would integrate with SendGrid, Twilio, Firebase, etc.
    """
    notification = Notification.query.get(notification_id)
    if not notification:
        logger.warning(f"Notification not found: {notification_id}")
        return False

    if notification.status == 'sent':
        logger.info(f"Notification already sent: {notification_id}")
        return True

    try:
        # Mock delivery — simulate sending
        logger.info(
            f"📤 SENDING [{notification.channel.upper()}] to user {notification.user_id}: "
            f"{notification.title}"
        )

        if notification.channel == 'email':
            _mock_send_email(notification)
        elif notification.channel == 'sms':
            _mock_send_sms(notification)
        elif notification.channel == 'push':
            _mock_send_push(notification)

        notification.status = 'sent'
        notification.sent_at = datetime.datetime.utcnow()
        db.session.commit()

        logger.info(f"✅ Notification sent: {notification_id} via {notification.channel}")
        return True

    except Exception as e:
        notification.retry_count += 1
        notification.error_message = str(e)

        if notification.retry_count >= notification.max_retries:
            notification.status = 'failed'
            logger.error(f"❌ Notification permanently failed: {notification_id} — {e}")
        else:
            logger.warning(f"⚠️ Notification retry {notification.retry_count}: {notification_id} — {e}")

        db.session.commit()
        return False


def _mock_send_email(notification):
    """Mock email sending — logs the email content."""
    logger.info(f"  📧 Email → user {notification.user_id}: Subject: {notification.title}")
    logger.info(f"     Body: {notification.message[:200]}")


def _mock_send_sms(notification):
    """Mock SMS sending."""
    logger.info(f"  📱 SMS → user {notification.user_id}: {notification.message[:160]}")


def _mock_send_push(notification):
    """Mock push notification sending."""
    logger.info(f"  🔔 Push → user {notification.user_id}: {notification.title}")


# =============================================================================
# Notification Queries
# =============================================================================

def get_user_notifications(user_id, page=1, per_page=20, status=None):
    """Get paginated notifications for a user."""
    query = Notification.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(
        Notification.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return pagination.items, pagination.total


def mark_as_read(notification_id, user_id):
    """Mark a notification as read."""
    notification = Notification.query.filter_by(
        id=notification_id, user_id=user_id
    ).first()
    if not notification:
        return None
    notification.read_at = datetime.datetime.utcnow()
    db.session.commit()
    return notification


def get_unread_count(user_id):
    """Get count of unread notifications."""
    return Notification.query.filter_by(
        user_id=user_id, read_at=None
    ).count()


def retry_failed_notifications():
    """Retry all failed notifications that haven't exceeded max retries."""
    failed = Notification.query.filter(
        Notification.status == 'failed',
        Notification.retry_count < Notification.max_retries,
    ).all()

    retried = 0
    for notification in failed:
        notification.status = 'pending'
        retried += 1

    if retried:
        db.session.commit()
        logger.info(f"Reset {retried} failed notifications for retry")

    return retried
