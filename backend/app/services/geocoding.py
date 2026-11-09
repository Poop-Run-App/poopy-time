"""Street addresses from coordinates, via OpenStreetMap's Nominatim.

Nominatim's usage policy allows at most one request per second and asks
for an identifying User-Agent. Results are © OpenStreetMap contributors.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .osm_toilets import USER_AGENT

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
MIN_SECONDS_BETWEEN_REQUESTS = 1.1

_last_request = 0.0


def reverse_geocode(lat, lng, timeout=30):
    """Closest street address, e.g. "2801 Alki Avenue Southwest", or None."""
    global _last_request
    wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)

    params = urllib.parse.urlencode({
        'lat': lat, 'lon': lng, 'format': 'jsonv2', 'zoom': 18, 'addressdetails': 1,
    })
    req = urllib.request.Request(f'{NOMINATIM_URL}?{params}', headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.load(res)
    finally:
        _last_request = time.monotonic()

    address = data.get('address') or {}
    # Some paths are named with just a number ("23"), which isn't a usable address
    streets = (address.get(key) for key in ('road', 'pedestrian', 'footway', 'path', 'cycleway'))
    street = next((s for s in streets if s and not s.strip().isdigit()), None)
    if not street:
        return None
    number = address.get('house_number')
    return f'{number} {street}' if number else street
