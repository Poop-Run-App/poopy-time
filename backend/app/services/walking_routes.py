"""Snap a hand-drawn path onto walkable paths, via a foot-profile OSRM server.

The path arrives as waypoints. Routing through them on the pedestrian
network keeps the route on the drawn line wherever that line is already
walkable, and moves any waypoint that isn't (a building, a lake, the
middle of a highway) onto the nearest walkable path.

By default this uses the public FOSSGIS server (routing.openstreetmap.de).
It is free but best-effort and meant for light use, so point ROUTING_URL at
your own OSRM foot instance (or a compatible provider) before real traffic.
Routing data is © OpenStreetMap contributors (ODbL).
"""
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

from .osm_toilets import USER_AGENT

DEFAULT_ROUTING_URL = 'https://routing.openstreetmap.de/routed-foot'
MAX_WAYPOINTS = 250
# Waypoints per routing request; consecutive requests share one waypoint
CHUNK_SIZE = 40
# A waypoint moved further than this counts as "adjusted". Hand-tracing a
# street is rarely closer than this, so smaller moves aren't worth flagging.
MOVED_THRESHOLD_METERS = 30
EARTH_RADIUS_METERS = 6371008.8


class RoutingError(Exception):
    """The routing service was unreachable or gave an unusable answer."""


class NoRouteError(RoutingError):
    """There is no walkable connection between the requested points."""


def _haversine_meters(a, b):
    d_lat = math.radians(b[0] - a[0])
    d_lng = math.radians(b[1] - a[1])
    h = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(d_lng / 2) ** 2)
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(h))


def _request_route(coords, timeout):
    """One routing request through `coords` ([(lat, lng), ...]).

    Returns {'points': [(lat, lng), ...], 'distance': meters,
    'snapped': [meters each waypoint was moved]}.
    """
    base = (os.getenv('ROUTING_URL') or DEFAULT_ROUTING_URL).rstrip('/')
    path = ';'.join(f'{lng:.6f},{lat:.6f}' for lat, lng in coords)
    query = urllib.parse.urlencode({
        'overview': 'full',
        'geometries': 'geojson',
        'steps': 'false',
        'alternatives': 'false',
        # Let the route turn around at a waypoint instead of looping the block
        'continue_straight': 'false',
    })
    # OSRM ignores the profile name in the URL ("driving" here): the server's
    # data decides it, and the foot server only knows walking.
    req = urllib.request.Request(
        f'{base}/route/v1/driving/{path}?{query}',
        headers={'User-Agent': USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.load(res)
    except urllib.error.HTTPError as e:
        # OSRM can report "no route" as an HTTP 400 with a JSON body
        try:
            data = json.load(e)
        except ValueError:
            raise RoutingError(f'Routing service returned HTTP {e.code}') from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise RoutingError(f'Routing service unavailable: {e}') from e

    code = data.get('code')
    if code in ('NoRoute', 'NoSegment'):
        raise NoRouteError(data.get('message') or code)
    if code != 'Ok' or not data.get('routes'):
        raise RoutingError(data.get('message') or f'Routing service returned {code}')

    route = data['routes'][0]
    return {
        'points': [(lat, lng) for lng, lat in route['geometry']['coordinates']],
        'distance': route['distance'],
        'snapped': [w.get('distance', 0) for w in data.get('waypoints', [])],
    }


def _route_span(coords, timeout):
    """Route through `coords`, working around stretches with no walkable link.

    If the whole span can't be routed, split it in half and try each half. A
    single pair that still can't be connected becomes a straight "gap" that
    the caller can show as unreachable.
    """
    try:
        return [_request_route(coords, timeout)]
    except NoRouteError:
        if len(coords) == 2:
            return [{
                'points': list(coords),
                'distance': _haversine_meters(coords[0], coords[1]),
                'snapped': [],
                'gap': True,
            }]
        mid = len(coords) // 2
        return _route_span(coords[:mid + 1], timeout) + _route_span(coords[mid:], timeout)


def snap_to_walkable(points, timeout=20):
    """Route through `points` ([(lat, lng), ...]) on walkable paths.

    Returns {'coordinates': [[lat, lng], ...], 'distance_meters': float,
    'adjusted': bool, 'gaps': [[[lat, lng], [lat, lng]], ...]}, where
    `adjusted` says some of the drawing was moved onto walkable paths and
    `gaps` are stretches that can't be walked to (drawn as straight lines).
    Raises RoutingError if the routing service can't be used.
    """
    pieces = []
    for start in range(0, len(points) - 1, CHUNK_SIZE - 1):
        chunk = points[start:start + CHUNK_SIZE]
        if len(chunk) >= 2:
            pieces.extend(_route_span(chunk, timeout))

    coordinates, gaps = [], []
    distance = 0.0
    moved = 0.0
    for piece in pieces:
        pts = [[lat, lng] for lat, lng in piece['points']]
        if piece.get('gap'):
            gaps.append(pts)
        if coordinates and pts and coordinates[-1] == pts[0]:
            pts = pts[1:]
        coordinates.extend(pts)
        distance += piece['distance']
        moved = max([moved, *piece['snapped']])

    return {
        'coordinates': coordinates,
        'distance_meters': round(distance, 1),
        'adjusted': moved > MOVED_THRESHOLD_METERS or bool(gaps),
        'gaps': gaps,
    }
