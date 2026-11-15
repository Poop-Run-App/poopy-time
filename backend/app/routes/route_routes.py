from flask import Blueprint, jsonify, request

from app.services.walking_routes import MAX_WAYPOINTS, RoutingError, snap_to_walkable
from .shared import token_required

route_bp = Blueprint('routes', __name__)


def _parse_points(data):
    """[[lat, lng], ...] from the request body, or ValueError."""
    points = data.get('points') if isinstance(data, dict) else None
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError('points must be a list of at least 2 [lat, lng] pairs')
    if len(points) > MAX_WAYPOINTS:
        raise ValueError(f'points can have at most {MAX_WAYPOINTS} entries')

    parsed = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('each point must be a [lat, lng] pair')
        lat, lng = point
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (lat, lng)):
            raise ValueError('lat and lng must be numbers')
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError('lat must be between -90 and 90 and lng between -180 and 180')
        parsed.append((float(lat), float(lng)))
    return parsed


@route_bp.route('/snap', methods=['POST'])
@token_required
def snap(current_user):
    """Move a hand-drawn path onto walkable paths.

    Body: {"points": [[lat, lng], ...]}. Returns {"route": {coordinates,
    distance_meters, adjusted, gaps}}; see services/walking_routes.py.
    """
    try:
        points = _parse_points(request.get_json(silent=True))
    except ValueError as e:
        return jsonify({'message': str(e)}), 400

    try:
        route = snap_to_walkable(points)
    except RoutingError as e:
        print(f'Route snapping failed: {e}')
        return jsonify({'message': "Couldn't reach the walking route service. Try again in a moment."}), 502
    return jsonify({'route': route}), 200
