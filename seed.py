"""
Notification Service — Seed data for demo purposes.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, UserPreference, NotificationRule, Notification


def seed():
    """Populate the database with sample notification preferences and rules."""
    app = create_app()

    with app.app_context():
        print("🌱 Seeding Notification Service database...")

        # Clear existing data
        Notification.query.delete()
        NotificationRule.query.delete()
        UserPreference.query.delete()
        db.session.commit()

        # --- User Preferences (matching user IDs from portfolio seed) ---
        prefs_data = [
            {'user_id': 1, 'email': True, 'sms': False, 'push': True,
             'quiet_start': '22:00', 'quiet_end': '07:00'},
            {'user_id': 2, 'email': True, 'sms': True, 'push': True,
             'quiet_start': None, 'quiet_end': None},
            {'user_id': 3, 'email': True, 'sms': False, 'push': False,
             'quiet_start': '23:00', 'quiet_end': '08:00'},
        ]
        for pd in prefs_data:
            pref = UserPreference(
                user_id=pd['user_id'],
                email_enabled=pd['email'],
                sms_enabled=pd['sms'],
                push_enabled=pd['push'],
                quiet_hours_start=pd['quiet_start'],
                quiet_hours_end=pd['quiet_end'],
            )
            db.session.add(pref)

        print(f"  ✅ Created {len(prefs_data)} user preferences")

        # --- Notification Rules ---
        rules_data = [
            # User 1 — john_doe
            {
                'user_id': 1, 'name': 'Large Transaction Alert',
                'rule_type': 'threshold',
                'conditions': {'field': 'total_amount', 'operator': '>', 'value': 5000},
            },
            {
                'user_id': 1, 'name': 'All Buy Alerts',
                'rule_type': 'transaction',
                'conditions': {'types': ['BUY'], 'tickers': []},
            },
            {
                'user_id': 1, 'name': 'AAPL Activity',
                'rule_type': 'transaction',
                'conditions': {'types': ['BUY', 'SELL'], 'tickers': ['AAPL']},
            },
            # User 2 — jane_smith
            {
                'user_id': 2, 'name': 'High Value Threshold',
                'rule_type': 'threshold',
                'conditions': {'field': 'total_amount', 'operator': '>', 'value': 10000},
            },
            {
                'user_id': 2, 'name': 'All Transaction Alerts',
                'rule_type': 'transaction',
                'conditions': {'types': ['BUY', 'SELL'], 'tickers': []},
            },
            # User 3 — bob_investor
            {
                'user_id': 3, 'name': 'Mega Transaction Alert',
                'rule_type': 'threshold',
                'conditions': {'field': 'total_amount', 'operator': '>', 'value': 15000},
            },
            {
                'user_id': 3, 'name': 'NVDA Tracker',
                'rule_type': 'transaction',
                'conditions': {'types': ['BUY', 'SELL'], 'tickers': ['NVDA', 'AMD']},
            },
        ]
        for rd in rules_data:
            rule = NotificationRule(
                user_id=rd['user_id'],
                name=rd['name'],
                rule_type=rd['rule_type'],
                conditions=rd['conditions'],
                is_active=True,
            )
            db.session.add(rule)

        db.session.commit()
        print(f"  ✅ Created {len(rules_data)} notification rules")

        print()
        print("📋 Seed data summary:")
        print("  User Preferences:")
        for pd in prefs_data:
            channels = []
            if pd['email']:
                channels.append('email')
            if pd['sms']:
                channels.append('sms')
            if pd['push']:
                channels.append('push')
            print(f"    • User {pd['user_id']}: channels={channels}, "
                  f"quiet={pd['quiet_start']}-{pd['quiet_end']}")

        print("  Notification Rules:")
        for rd in rules_data:
            print(f"    • User {rd['user_id']}: {rd['name']} ({rd['rule_type']})")

        print("\n✅ Seeding complete!")


if __name__ == '__main__':
    seed()
