"""
Shared authentication utilities — JWT token generation, verification, and decorators.
"""
import jwt
import datetime
import functools
from flask import request, jsonify, g


_jwt_secret = None
_jwt_algorithm = 'HS256'
_jwt_expiry_hours = 24


def init_auth(secret, algorithm='HS256', expiry_hours=24):
    """Initialize auth module with JWT configuration."""
    global _jwt_secret, _jwt_algorithm, _jwt_expiry_hours
    _jwt_secret = secret
    _jwt_algorithm = algorithm
    _jwt_expiry_hours = expiry_hours


def generate_token(user_id, username, email):
    """Generate a JWT token for an authenticated user."""
    now = datetime.datetime.utcnow()
    payload = {
        'user_id': user_id,
        'username': username,
        'email': email,
        'iat': now,
        'exp': now + datetime.timedelta(hours=_jwt_expiry_hours),
    }
    return jwt.encode(payload, _jwt_secret, algorithm=_jwt_algorithm)


def decode_token(token):
    """Decode and verify a JWT token. Raises on invalid/expired tokens."""
    return jwt.decode(token, _jwt_secret, algorithms=[_jwt_algorithm])


def require_auth(f):
    """Decorator that enforces JWT authentication on a route.

    After successful auth, sets g.current_user with the token payload.
    Also supports internal service-to-service calls via X-User-ID header.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Check for internal service headers first (from API Gateway)
        user_id = request.headers.get('X-User-ID')
        if user_id:
            g.current_user = {
                'user_id': int(user_id),
                'username': request.headers.get('X-Username', ''),
                'email': request.headers.get('X-Email', ''),
            }
            return f(*args, **kwargs)

        # Fall back to JWT token validation
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required', 'code': 'AUTH_REQUIRED'}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            payload = decode_token(token)
            g.current_user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired', 'code': 'TOKEN_EXPIRED'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token', 'code': 'INVALID_TOKEN'}), 401

        return f(*args, **kwargs)
    return decorated
