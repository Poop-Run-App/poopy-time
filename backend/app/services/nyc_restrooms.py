"""New York City public restrooms, from NYC Open Data.

Data is from the City of New York's "Public Restrooms" dataset (i7jb-7jku)
on NYC Open Data.
"""
import hashlib
import json
import re
import urllib.parse
import urllib.request

from .osm_toilets import USER_AGENT

DATASET_URL = 'https://data.cityofnewyork.us/resource/i7jb-7jku.json'
PAGE_SIZE = 5000
SOURCE = 'nyc_opendata'
# The dataset has no stable ID, so city_id is this prefix plus a hash of the
# name, location type and position. It also tells NYC rows from Seattle's.
ID_PREFIX = 'nyc:'

# Rows outside this are bad geocodes, not nearby restrooms
BOUNDS = (40.40, -74.30, 40.95, -73.65)

_TIME = r'(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?'
_RANGE = re.compile(
    rf'^(?:every\s*day|daily)?\s*{_TIME}\s*[-–]\s*{_TIME}\s*(?:daily)?\s*(?:,\s*(.+))?$',
    re.IGNORECASE,
)
_ALL_DAY = {'24 hours', 'open 24/7', '24/7'}

_STATUS = {
    'OPERATIONAL': ('open', None),
    'NOT OPERATIONAL': ('closed', 'Not operating'),
    'CLOSED FOR CONSTRUCTION': ('closed', 'Closed for construction'),
    'CLOSED': ('closed', 'Temporarily closed'),
}
_GENDER = {
    'multi-stall w/m restrooms': 'separate',
    'single-stall w/m restrooms': 'separate',
    'single-stall all gender restroom(s)': 'unisex',
    'single -stall all gender restroom(s)': 'unisex',
    'multi-stall all gender restrooms': 'unisex',
    # An all-gender room is available alongside the men's and women's rooms
    'both single-stall all gender and multi-stall w/m': 'unisex',
}
_ACCESSIBILITY_NOTES = {
    'PARTIALLY ACCESSIBLE': 'Partially wheelchair accessible',
    'LIMITED ACCESSIBILITY': 'Limited wheelchair accessibility',
}


def fetch_restrooms(timeout=60):
    """Every row in the dataset."""
    rows, offset = [], 0
    while True:
        params = urllib.parse.urlencode({'$limit': PAGE_SIZE, '$offset': offset, '$order': ':id'})
        req = urllib.request.Request(f'{DATASET_URL}?{params}', headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            page = json.load(res)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def located(rows):
    """(city_id, lat, lng, row) for each row with a usable position."""
    out, counts = [], {}
    for row in rows:
        try:
            lat, lng = float(row['latitude']), float(row['longitude'])
        except (KeyError, TypeError, ValueError):
            continue
        south, west, north, east = BOUNDS
        if not (south <= lat <= north and west <= lng <= east):
            continue
        key = '|'.join([
            _text(row.get('facility_name')).lower(),
            _text(row.get('location_type')).lower(),
            f'{lat:.5f}',
            f'{lng:.5f}',
        ])
        city_id = ID_PREFIX + hashlib.sha256(key.encode()).hexdigest()[:32]
        counts[city_id] = counts.get(city_id, 0) + 1
        if counts[city_id] > 1:
            city_id = f'{city_id}-{counts[city_id]}'
        out.append((city_id, lat, lng, row))
    return out


def owns(city_id):
    return bool(city_id) and city_id.startswith(ID_PREFIX)


def display_name(row):
    name = _text(row.get('facility_name')) or 'Public restroom'
    lowered = name.lower()
    if 'restroom' not in lowered and 'toilet' not in lowered and 'bathroom' not in lowered:
        name = f'{name} restroom'
    return name[:150]


def parse_hours(row):
    """(open_hour, close_hour, hours_note), or None when the city lists no hours.

    A single daily range like "8am-4pm" becomes hours; anything else (a
    different time each weekday, "7am - dusk") is kept as text.
    """
    hours = ' '.join(_text(row.get('hours_of_operation')).split())
    seasonal = _text(row.get('open')).upper() == 'SEASONAL'
    if not hours:
        return (None, None, 'Seasonal') if seasonal else None
    season_note = ', seasonal' if seasonal and 'season' not in hours.lower() else ''

    if hours.lower() in _ALL_DAY:
        return 0, 24, ('24 hours' + season_note) if season_note else None
    match = _RANGE.match(hours)
    if match:
        open_hour = _hour(match[1], match[2], match[3])
        close_hour = _hour(match[4], match[5], match[6]) or 24
        if open_hour != close_hour:
            note = hours if match[7] or season_note else None
            return open_hour, close_hour, (note + season_note)[:255] if note else None
    # Weekly schedules come one day per line
    text = '; '.join(part.strip() for part in _text(row.get('hours_of_operation')).replace('\t', ' ').splitlines() if part.strip())
    return None, None, (text + season_note)[:255]


def parse_status(row):
    """(status, status_reason) from the city's status."""
    if _text(row.get('open')).upper() == 'FUTURE':
        return 'closed', 'Not open yet'
    return _STATUS.get(_text(row.get('status')).upper(), (None, None))


def is_accessible(row):
    """True or False when the city says, None when it doesn't."""
    accessibility = _text(row.get('accessibility')).upper()
    if not accessibility:
        return None
    return accessibility == 'FULLY ACCESSIBLE'


def gender(row):
    return _GENDER.get(_text(row.get('restroom_type')).lower())


def notes(row):
    parts = []
    accessibility_note = _ACCESSIBILITY_NOTES.get(_text(row.get('accessibility')).upper())
    if accessibility_note:
        parts.append(accessibility_note)
    changing = _text(row.get('changing_stations'))
    if changing.lower() == 'yes':
        parts.append('Changing table')
    elif changing.lower().startswith('yes, in '):
        parts.append(f'Changing table in {changing[len("yes, in "):]}')
    additional = _text(row.get('additional_notes'))
    if additional:
        parts.append(additional.rstrip('.'))
    return '. '.join(parts) or None


def _text(value):
    text = str(value or '').strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _hour(hour, minutes, meridiem):
    hour = int(hour) % 12 + (12 if meridiem.lower() == 'p' else 0)
    return hour + int(minutes or 0) / 60
