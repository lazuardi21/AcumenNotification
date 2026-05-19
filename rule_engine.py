"""
Notification Service — Rule evaluation engine.

Evaluates notification rules against incoming portfolio events to determine
which notifications should be generated.
"""
import logging

logger = logging.getLogger(__name__)


def evaluate_rules(rules, event_data):
    """Evaluate a list of notification rules against an event.

    Args:
        rules: List of NotificationRule objects
        event_data: Dict with event payload from portfolio service

    Returns:
        List of matching rules that should trigger notifications
    """
    matching_rules = []

    for rule in rules:
        if not rule.is_active:
            continue

        try:
            if rule.rule_type == 'threshold' and _check_threshold(rule.conditions, event_data):
                matching_rules.append(rule)
            elif rule.rule_type == 'transaction' and _check_transaction(rule.conditions, event_data):
                matching_rules.append(rule)
            elif rule.rule_type == 'daily_summary':
                # Daily summaries are triggered by Celery Beat, not individual events
                continue
        except Exception as e:
            logger.error(f"Error evaluating rule {rule.id}: {e}")
            continue

    logger.info(f"Evaluated {len(rules)} rules → {len(matching_rules)} matched")
    return matching_rules


def _check_threshold(conditions, event_data):
    """Check if a transaction exceeds a threshold.

    Conditions format: {"field": "total_amount", "operator": ">", "value": 10000}
    """
    transaction = event_data.get('transaction', {})
    field = conditions.get('field', 'total_amount')
    operator = conditions.get('operator', '>')
    threshold = conditions.get('value', 0)

    actual_value = transaction.get(field, 0)

    operators = {
        '>': lambda a, b: a > b,
        '>=': lambda a, b: a >= b,
        '<': lambda a, b: a < b,
        '<=': lambda a, b: a <= b,
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
    }

    check_fn = operators.get(operator, operators['>'])
    result = check_fn(actual_value, threshold)

    if result:
        logger.info(f"Threshold rule matched: {field} {operator} {threshold} (actual: {actual_value})")

    return result


def _check_transaction(conditions, event_data):
    """Check if a transaction matches type and ticker filters.

    Conditions format: {"types": ["BUY", "SELL"], "tickers": ["AAPL", "GOOGL"]}
    """
    transaction = event_data.get('transaction', {})
    txn_type = transaction.get('type', '')
    ticker = transaction.get('ticker', '')

    allowed_types = conditions.get('types', ['BUY', 'SELL'])
    allowed_tickers = conditions.get('tickers', [])  # Empty = all tickers

    type_match = txn_type in allowed_types
    ticker_match = not allowed_tickers or ticker in allowed_tickers

    return type_match and ticker_match


def generate_notification_content(rule, event_data):
    """Generate notification title and message based on rule type and event data.

    Returns:
        tuple: (title, message, notification_type)
    """
    transaction = event_data.get('transaction', {})
    portfolio_name = event_data.get('portfolio_name', 'Unknown Portfolio')

    if rule.rule_type == 'threshold':
        threshold = rule.conditions.get('value', 0)
        title = f"🚨 Threshold Alert — {transaction.get('ticker', 'N/A')}"
        message = (
            f"Transaction of ${transaction.get('total_amount', 0):,.2f} "
            f"({transaction.get('type', '')} {transaction.get('quantity', 0)} "
            f"{transaction.get('ticker', '')} @ ${transaction.get('price', 0):,.2f}) "
            f"exceeded your threshold of ${threshold:,.2f} "
            f"in portfolio '{portfolio_name}'."
        )
        return title, message, 'threshold_alert'

    elif rule.rule_type == 'transaction':
        title = f"📊 Transaction Alert — {transaction.get('type', '')} {transaction.get('ticker', '')}"
        message = (
            f"{transaction.get('type', '')} {transaction.get('quantity', 0)} shares of "
            f"{transaction.get('ticker', '')} at ${transaction.get('price', 0):,.2f} "
            f"(Total: ${transaction.get('total_amount', 0):,.2f}) "
            f"in portfolio '{portfolio_name}'."
        )
        return title, message, 'transaction_alert'

    else:
        title = f"Portfolio Update — {portfolio_name}"
        message = f"Activity detected in portfolio '{portfolio_name}'."
        return title, message, 'general'
