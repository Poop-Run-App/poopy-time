from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from app import db, bcrypt
from app.models.userDB import User
from .shared import token_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    display_name = (data.get('display_name') or '').strip() or None

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'An account with that email already exists'}), 409

    user = User(
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
        display_name=display_name,
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': user.to_dict()}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({'message': 'Invalid email or password'}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': user.to_dict()}), 200


@auth_bp.route('/me', methods=['GET'])
@token_required
def me(current_user):
    return jsonify({'user': current_user.to_dict()}), 200
