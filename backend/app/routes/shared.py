from functools import wraps

from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app import db
from app.models.userDB import User


def token_required(f):
    """Injects the authenticated User as the first argument of the route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({'message': 'Invalid token: no user identity'}), 401

            current_user = db.session.get(User, int(user_id))
            if not current_user:
                return jsonify({'message': 'User not found'}), 404
            if not current_user.is_active:
                return jsonify({'message': 'Account deactivated'}), 403

            return f(current_user, *args, **kwargs)

        except ExpiredSignatureError:
            return jsonify({'message': 'Token has expired', 'error_code': 'TOKEN_EXPIRED'}), 401
        except InvalidTokenError as e:
            return jsonify({'message': f'Invalid token: {e}', 'error_code': 'INVALID_TOKEN'}), 401
        except Exception as e:  # noqa: BLE001
            print(f"Unexpected JWT error: {e}")
            return jsonify({'message': 'Authentication failed', 'error_code': 'AUTH_ERROR'}), 401

    return decorated
