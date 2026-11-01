import math

from flask import Blueprint, jsonify, request

from app import db
from app.models.bathroomDB import Bathroom
from .shared import token_required

bathroom_bp = Blueprint('bathrooms', __name__)

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LAT = 69.0
MAX_RADIUS_MILES = 25
MAX_LIMIT = 50


def distance_miles(lat1, lng1, lat2, lng2):
    """Great-circle (haversine) distance."""
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    h = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def _parse_float(value, name, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be a number')
    if not low <= number <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return number


def _parse_hour(value, name):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 24:
        raise ValueError(f'{name} must be a whole number from 0 to 24')
    return value


@bathroom_bp.route('/nearby', methods=['GET'])
@token_required
def nearby(current_user):
    try:
        lat = _parse_float(request.args.get('lat'), 'lat', -90, 90)
        lng = _parse_float(request.args.get('lng'), 'lng', -180, 180)
        radius = _parse_float(request.args.get('radius_miles', 1), 'radius_miles', 0.01, MAX_RADIUS_MILES)
        limit = int(_parse_float(request.args.get('limit', 20), 'limit', 1, MAX_LIMIT))
    except ValueError as e:
        return jsonify({'message': str(e)}), 400

    # Narrow with a bounding box in SQL, then measure exactly in Python
    d_lat = radius / MILES_PER_DEGREE_LAT
    d_lng = radius / (MILES_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.01))
    candidates = Bathroom.query.filter(
        Bathroom.latitude.between(lat - d_lat, lat + d_lat),
        Bathroom.longitude.between(lng - d_lng, lng + d_lng),
    ).all()

    results = []
    for b in candidates:
        miles = distance_miles(lat, lng, b.latitude, b.longitude)
        if miles <= radius:
            results.append({**b.to_dict(), 'distance_miles': round(miles, 2)})
    results.sort(key=lambda r: r['distance_miles'])

    return jsonify({'bathrooms': results[:limit]}), 200


@bathroom_bp.route('/<int:bathroom_id>', methods=['GET'])
@token_required
def get_bathroom(current_user, bathroom_id):
    bathroom = db.session.get(Bathroom, bathroom_id)
    if not bathroom:
        return jsonify({'message': 'Bathroom not found'}), 404
    return jsonify({'bathroom': bathroom.to_dict()}), 200


@bathroom_bp.route('', methods=['POST'])
@token_required
def create_bathroom(current_user):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'message': 'Name is required'}), 400

    try:
        latitude = _parse_float(data.get('latitude'), 'latitude', -90, 90)
        longitude = _parse_float(data.get('longitude'), 'longitude', -180, 180)
        open_hour = _parse_hour(data.get('open_hour'), 'open_hour')
        close_hour = _parse_hour(data.get('close_hour'), 'close_hour')
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    if (open_hour is None) != (close_hour is None):
        return jsonify({'message': 'Give both open_hour and close_hour, or neither for 24 hours'}), 400

    bathroom = Bathroom(
        name=name,
        address=(data.get('address') or '').strip() or None,
        latitude=latitude,
        longitude=longitude,
        open_hour=open_hour,
        close_hour=close_hour,
        is_accessible=bool(data.get('is_accessible')),
        notes=(data.get('notes') or '').strip() or None,
        created_by_id=current_user.id,
    )
    db.session.add(bathroom)
    db.session.commit()
    return jsonify({'bathroom': bathroom.to_dict()}), 201
