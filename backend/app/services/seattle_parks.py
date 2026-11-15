"""Seattle Parks and Recreation public restrooms, from the City's open data.

Data is © City of Seattle, Seattle Parks and Recreation. The layer is
"Park Restrooms" on Seattle's open data hub, refreshed by the City.
"""
import json
import re
import urllib.parse
import urllib.request

from .osm_toilets import USER_AGENT

LAYER_URL = 'https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/Parks_Restrooms/FeatureServer/0'

# Bounds that cover every Seattle Parks restroom, for limiting which
# bathrooms an import may touch
BOUNDS = (47.48, -122.44, 47.74, -122.24)

_HOURS = re.compile(r'^(\d{1,2})\s*AM\s*-\s*(\d{1,2})(?:\s*/\s*(\d{1,2}))?\s*PM$', re.IGNORECASE)

_REASONS = {
    'SEASON': 'Closed for the season',
    'REPAIR': 'Closed for repair',
    'CAPITAL PROJECT-PLANNED': 'Closed for construction',
    'CAPITAL PROJECT-UNPLANNED': 'Closed for construction',
    'OTHER': 'Temporarily closed',
}
_USAGE = {
    'EVENTS / PROGRAMS ONLY': 'Events and programs only',
    'METRO TRANSIT ONLY': 'Metro Transit staff only',
}
_MONTHS = {'JAN': 'January', 'FEB': 'February', 'MAR': 'March', 'APR': 'April', 'MAY': 'May',
           'JUN': 'June', 'JUL': 'July', 'AUG': 'August', 'SEP': 'September', 'OCT': 'October',
           'NOV': 'November', 'DEC': 'December'}
_ABBREVIATIONS = {'CC': 'Community Center', 'PF': 'Playfield', 'PG': 'Playground', 'PK': 'Park',
                  'CS': 'Comfort Station', 'SH': 'Shelterhouse', 'N': 'North', 'S': 'South',
                  'E': 'East', 'W': 'West', 'SW': 'Southwest', 'NE': 'Northeast', 'AVE': 'Avenue',
                  'MT': 'Mount'}
_LOWERCASE = {'and', 'of', 'the', 'at'}


def fetch_restrooms(timeout=60):
    """Every restroom in the layer, as GeoJSON features (WGS84)."""
    params = urllib.parse.urlencode({'where': '1=1', 'outFields': '*', 'outSR': 4326, 'f': 'geojson'})
    req = urllib.request.Request(f'{LAYER_URL}/query?{params}', headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)['features']


def is_public(props):
    return props.get('OPENTOPUBLIC') == 'YES' and props.get('LIFECYCLESTATUSTXT') == 'A'


def record_url(city_id):
    """Link to the City's record for one restroom."""
    params = urllib.parse.urlencode({'where': f"AMWOID='{city_id}'", 'outFields': '*', 'f': 'html'})
    return f'{LAYER_URL}/query?{params}'


def parse_hours(props):
    """(open_hour, close_hour, hours_note), or None to leave hours as they are.

    "7AM - 7/9PM" means the closing time varies over the year; the earlier
    time is used so the app never calls a closed restroom open.
    """
    hours = (props.get('HOURS') or '').strip()
    seasonal = (props.get('SEASON') or '').upper() == 'SEASONAL'
    close_month = _MONTHS.get((props.get('SEASONCLOSEDATE') or '').upper())
    season_note = ''
    if seasonal:
        season_note = f', seasonal (closes in {close_month})' if close_month else ', seasonal'

    match = _HOURS.match(hours)
    if match:
        open_hour, close_pm, late_pm = int(match[1]), int(match[2]), match[3]
        note = f'{open_hour}am-{close_pm}pm'
        if late_pm:
            note += f' (until {late_pm}pm part of the year)'
        return open_hour, close_pm + 12, note + season_note
    if hours.upper() == 'PARK HOURS':
        return None, None, 'Park hours' + season_note
    if seasonal:
        return None, None, 'Seasonal' + season_note[len(', seasonal'):]
    return None


def parse_status(props):
    """(status, status_reason) from the City's current status."""
    status = (props.get('CURRENTSTATUS') or '').upper()
    if status == 'CLOSED':
        return 'closed', _REASONS.get((props.get('RSNCLOSED') or '').upper(), 'Temporarily closed')
    usage = _USAGE.get((props.get('USAGE') or '').upper())
    if status == 'LIMITED USE' or usage:
        return 'limited', usage or 'Limited use'
    if status == 'OPEN':
        return 'open', None
    return None, None


def display_name(props):
    """"WESTCREST PARK NORTH RESTROOM" -> "Westcrest Park North restroom"."""
    text = props.get('DESCRIPTION') or f"{props.get('PARK') or 'Park'} restroom"
    words = text.replace('`', "'").split()
    out = []
    for i, word in enumerate(words):
        upper = word.upper()
        if upper in _ABBREVIATIONS:
            out.append(_ABBREVIATIONS[upper])
        elif upper == 'RESTROOM':
            out.append('restroom')
        elif i and word.lower() in _LOWERCASE:
            out.append(word.lower())
        else:
            out.append(word.capitalize())
    name = ' '.join(out)
    return name if 'restroom' in name else f'{name} restroom'
