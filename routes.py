"""
Notification Service — Flask route definitions.
"""
import logging
from flask import Blueprint, request, jsonify, g
from models import db, Notification, UserPreference, NotificationRule
from shared.auth import require_auth
import services

logger = logging.getLogger(__name__)

# =============================================================================
# Notification Routes
# =============================================================================
notification_bp = Blueprint('notification', __name__, url_prefix='/api/notifications')


@notification_bp.route('', methods=['GET'])
@require_auth
def list_notifications():
    """List paginated notifications for the current user."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')

    notifications, total = services.get_user_notifications(
        g.current_user['user_id'], page, per_page, status,
    )
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'total': total,
        'page': page,
        'per_page': per_page,
        'unread_count': services.get_unread_count(g.current_user['user_id']),
    })


@notification_bp.route('/<int:notification_id>/read', methods=['PATCH'])
@require_auth
def mark_read(notification_id):
    """Mark a notification as read."""
    notification = services.mark_as_read(notification_id, g.current_user['user_id'])
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    return jsonify({'notification': notification.to_dict()})


@notification_bp.route('/read-all', methods=['PATCH'])
@require_auth
def mark_all_read():
    """Mark all notifications as read for the current user."""
    import datetime
    count = Notification.query.filter_by(
        user_id=g.current_user['user_id'], read_at=None
    ).update({'read_at': datetime.datetime.utcnow()})
    db.session.commit()
    return jsonify({'message': f'{count} notifications marked as read'})


# =============================================================================
# User Preference Routes
# =============================================================================
preference_bp = Blueprint('preference', __name__, url_prefix='/api/preferences')


@preference_bp.route('', methods=['GET'])
@require_auth
def get_preferences():
    """Get notification preferences for the current user."""
    prefs = UserPreference.query.filter_by(user_id=g.current_user['user_id']).first()
    if not prefs:
        # Return defaults
        return jsonify({'preferences': {
            'user_id': g.current_user['user_id'],
            'email_enabled': True,
            'sms_enabled': False,
            'push_enabled': True,
            'quiet_hours_start': None,
            'quiet_hours_end': None,
        }})
    return jsonify({'preferences': prefs.to_dict()})


@preference_bp.route('', methods=['PUT'])
@require_auth
def update_preferences():
    """Create or update notification preferences."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    user_id = g.current_user['user_id']
    prefs = UserPreference.query.filter_by(user_id=user_id).first()

    if not prefs:
        prefs = UserPreference(user_id=user_id)
        db.session.add(prefs)

    if 'email_enabled' in data:
        prefs.email_enabled = bool(data['email_enabled'])
    if 'sms_enabled' in data:
        prefs.sms_enabled = bool(data['sms_enabled'])
    if 'push_enabled' in data:
        prefs.push_enabled = bool(data['push_enabled'])
    if 'quiet_hours_start' in data:
        prefs.quiet_hours_start = data['quiet_hours_start']
    if 'quiet_hours_end' in data:
        prefs.quiet_hours_end = data['quiet_hours_end']

    db.session.commit()
    logger.info(f"Preferences updated for user {user_id}")
    return jsonify({'preferences': prefs.to_dict()})


# =============================================================================
# Notification Rule Routes
# =============================================================================
rule_bp = Blueprint('rule', __name__, url_prefix='/api/rules')


@rule_bp.route('', methods=['POST'])
@require_auth
def create_rule():
    """Create a new notification rule."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    required = ['name', 'rule_type', 'conditions']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    valid_types = ['threshold', 'transaction', 'daily_summary']
    if data['rule_type'] not in valid_types:
        return jsonify({'error': f'Invalid rule_type. Must be one of: {valid_types}'}), 400

    rule = NotificationRule(
        user_id=g.current_user['user_id'],
        name=data['name'],
        rule_type=data['rule_type'],
        conditions=data['conditions'],
        is_active=data.get('is_active', True),
    )
    db.session.add(rule)
    db.session.commit()

    logger.info(f"Rule created: {rule.id} ({rule.rule_type}) for user {rule.user_id}")
    return jsonify({'rule': rule.to_dict()}), 201


@rule_bp.route('', methods=['GET'])
@require_auth
def list_rules():
    """List all notification rules for the current user."""
    rules = NotificationRule.query.filter_by(
        user_id=g.current_user['user_id']
    ).order_by(NotificationRule.created_at.desc()).all()

    return jsonify({
        'rules': [r.to_dict() for r in rules],
        'total': len(rules),
    })


@rule_bp.route('/<int:rule_id>', methods=['PUT'])
@require_auth
def update_rule(rule_id):
    """Update a notification rule."""
    data = request.get_json()
    rule = NotificationRule.query.filter_by(
        id=rule_id, user_id=g.current_user['user_id']
    ).first()
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    if 'name' in data:
        rule.name = data['name']
    if 'conditions' in data:
        rule.conditions = data['conditions']
    if 'is_active' in data:
        rule.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'rule': rule.to_dict()})


@rule_bp.route('/<int:rule_id>', methods=['DELETE'])
@require_auth
def delete_rule(rule_id):
    """Delete a notification rule."""
    rule = NotificationRule.query.filter_by(
        id=rule_id, user_id=g.current_user['user_id']
    ).first()
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    db.session.delete(rule)
    db.session.commit()
    return jsonify({'message': 'Rule deleted'})
