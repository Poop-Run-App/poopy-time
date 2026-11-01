"""Public toilets from OpenStreetMap, via the Overpass API.

OSM data is © OpenStreetMap contributors (ODbL) and must be credited
wherever it is shown.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# Public Overpass servers are often busy, so fall back to a mirror
OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
USER_AGENT = 'PoopyTime/0.1 (bathroom finder; https://github.com/Poop-Run-App/poopy-time)'

# (south, west, north, east)
CITY_BOUNDS = {
    'seattle': (47.4810, -122.4598, 47.7341, -122.2245),
}

_SIMPLE_HOURS = re.compile(r'^(?:Mo-Su\s+)?(\d{2}):00-(\d{2}):00$')


# Named places that unnamed toilets get named after ("Volunteer Park restroom")
_PLACE_TAGS = 'park|playground|nature_reserve|garden|sports_centre|stadium|golf_course|marina|zoo|attraction|theme_park'


def fetch_toilets(bounds, timeout=90, retry_waits=(15, 30, 60), log=print):
    """(toilets, places) inside the bounding box.

    toilets are raw OSM elements tagged amenity=toilets; places are named
    parks and attractions with their bounding boxes.
    """
    south, west, north, east = bounds
    bbox = f'{south},{west},{north},{east}'
    query = f"""
        [out:json][timeout:{timeout}];
        nwr["amenity"="toilets"]({bbox});
        out center tags;
        nwr[name][~"^(leisure|tourism)$"~"^({_PLACE_TAGS})$"]({bbox});
        out bb tags;
    """
    body = urllib.parse.urlencode({'data': query}).encode()
    errors = []
    for attempt, wait in enumerate((0, *retry_waits)):
        if wait:
            log(f'Overpass servers are busy, retrying in {wait}s...')
            time.sleep(wait)
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        req = urllib.request.Request(url, data=body, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 30) as res:
                elements = json.load(res)['elements']
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            errors.append(f'{url}: {e}')
            continue
        toilets = [e for e in elements if e.get('tags', {}).get('amenity') == 'toilets']
        places = [e for e in elements if 'bounds' in e and e.get('tags', {}).get('amenity') != 'toilets']
        return toilets, places
    raise RuntimeError('All Overpass servers failed, try again in a few minutes.\n' + '\n'.join(errors))


# Places with a bounding box bigger than this (in square degrees, about
# 4 km x 3 km in Seattle) are skipped. Spread-out places such as a national
# park with sites in two states would otherwise name toilets across the city.
MAX_PLACE_BOX = 0.0015


def _place_name_for(lat, lng, places):
    """Name of the smallest place whose bounding box contains the point."""
    best, best_size = None, None
    for place in places:
        b = place['bounds']
        if b['minlat'] <= lat <= b['maxlat'] and b['minlon'] <= lng <= b['maxlon']:
            size = (b['maxlat'] - b['minlat']) * (b['maxlon'] - b['minlon'])
            if size > MAX_PLACE_BOX:
                continue
            if best_size is None or size < best_size:
                best, best_size = place['tags']['name'], size
    return best


def parse_hours(opening_hours):
    """OSM opening_hours -> (open_hour, close_hour, hours_note).

    Only "24/7" and a single daily range like "08:00-22:00" become hours;
    anything else is kept as text so the app can show it as-is.
    """
    if not opening_hours:
        return None, None, 'Hours unknown'
    value = opening_hours.strip()
    if value == '24/7':
        return 0, 24, None
    match = _SIMPLE_HOURS.match(value)
    if match:
        open_hour, close_hour = int(match[1]), int(match[2])
        if 0 <= open_hour <= 24 and 0 <= close_hour <= 24 and open_hour != close_hour:
            return open_hour, close_hour, None
    return None, None, value[:255]


def _notes(tags):
    notes = []
    if tags.get('fee') == 'yes':
        notes.append('Fee required')
    if tags.get('access') == 'customers':
        notes.append('Customers only')
    if tags.get('unisex') == 'yes':
        notes.append('Unisex')
    if tags.get('changing_table') == 'yes':
        notes.append('Changing table')
    # Descriptions are often just the name again ("Carkeek Park Restroom")
    description = tags.get('description')
    if description and 'restroom' not in description.lower() and 'toilet' not in description.lower():
        notes.append(description)
    return '. '.join(notes) or None


def to_bathroom_fields(element, places=()):
    """Bathroom column values for one OSM element, or None to skip it."""
    tags = element.get('tags', {})
    if tags.get('access') in ('private', 'no'):
        return None

    # Ways and relations come back with a computed center point
    point = element.get('center', element)
    if 'lat' not in point or 'lon' not in point:
        return None

    name = (tags.get('name')
            or _place_name_for(point['lat'], point['lon'], places)
            or tags.get('operator'))
    name = f'{name} restroom' if name and 'restroom' not in name.lower() and 'toilet' not in name.lower() else name
    address = ' '.join(filter(None, [tags.get('addr:housenumber'), tags.get('addr:street')])) or None
    open_hour, close_hour, hours_note = parse_hours(tags.get('opening_hours'))

    return {
        'osm_id': f"{element['type']}/{element['id']}",
        'name': (name or 'Public restroom')[:150],
        'address': address[:255] if address else None,
        'latitude': point['lat'],
        'longitude': point['lon'],
        'open_hour': open_hour,
        'close_hour': close_hour,
        'hours_note': hours_note,
        'is_accessible': tags.get('wheelchair') == 'yes',
        'notes': _notes(tags),
        'source': 'osm',
    }
