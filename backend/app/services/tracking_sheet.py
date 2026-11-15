"""Rows from the team's bathroom tracking sheets (one Google Sheet per state,
one tab per city), exported as CSV.

Columns: Database ID, Name, Address, Open Hour, Close Hour, Wheelchair
Accessible, Gender, Latitude, Longitude, Link, osm_id, Closed. Hours are
0-24 and may be fractional (17.5 = 5:30pm). osm_id is OSM's bare number,
without the node/way type.
"""
import csv
import json
import urllib.parse
import urllib.request

from .osm_toilets import OVERPASS_URLS, USER_AGENT

GENDERS = {
    'unisex': 'unisex',
    "separate men's and women's": 'separate',
    'men only': 'men',
    'women only': 'women',
}
REQUIRED = ('Name', 'Latitude', 'Longitude')


class SheetError(ValueError):
    pass


def _hour(value, row_number, column):
    value = (value or '').strip()
    if not value:
        return None
    try:
        hour = float(value)
    except ValueError:
        raise SheetError(f'Row {row_number}: {column} "{value}" is not a number')
    if not 0 <= hour <= 24:
        raise SheetError(f'Row {row_number}: {column} {value} is outside 0-24')
    return hour


def read_rows(path):
    """Bathroom fields for each sheet row, as dicts. Raises SheetError on bad data."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SheetError(f'Missing columns: {", ".join(missing)}')
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if not any((v or '').strip() for v in row.values()):
                continue
            name = (row.get('Name') or '').strip()
            if not name:
                raise SheetError(f'Row {row_number}: Name is empty')
            try:
                lat, lng = float(row['Latitude']), float(row['Longitude'])
            except (TypeError, ValueError):
                raise SheetError(f'Row {row_number}: Latitude/Longitude must be numbers')
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise SheetError(f'Row {row_number}: Latitude/Longitude out of range')

            open_hour = _hour(row.get('Open Hour'), row_number, 'Open Hour')
            close_hour = _hour(row.get('Close Hour'), row_number, 'Close Hour')
            if (open_hour is None) != (close_hour is None):
                # One half of the range without the other isn't usable
                open_hour = close_hour = None

            gender_text = (row.get('Gender') or '').strip().lower()
            if gender_text and gender_text not in GENDERS:
                raise SheetError(f'Row {row_number}: unknown Gender "{row.get("Gender")}"')

            osm_number = (row.get('osm_id') or '').strip()
            rows.append({
                'row_number': row_number,
                'name': name[:150],
                'address': (row.get('Address') or '').strip()[:255] or None,
                'open_hour': open_hour,
                'close_hour': close_hour,
                'is_accessible': (row.get('Wheelchair Accessible') or '').strip().upper() == 'TRUE',
                'gender': GENDERS.get(gender_text),
                'latitude': lat,
                'longitude': lng,
                'closed': (row.get('Closed') or '').strip().upper() == 'TRUE',
                'osm_number': osm_number if osm_number.isdigit() else None,
            })
    return rows


def resolve_osm_types(numbers, timeout=90):
    """{"123": "node/123", ...} for the given bare OSM numbers that are
    toilets in OSM (looked up as nodes and ways in one Overpass request)."""
    numbers = sorted(set(numbers))
    if not numbers:
        return {}
    ids = ','.join(numbers)
    query = f'[out:json][timeout:{timeout}];(node(id:{ids});way(id:{ids}););out ids tags;'
    body = urllib.parse.urlencode({'data': query}).encode()
    errors = []
    for url in OVERPASS_URLS:
        req = urllib.request.Request(url, data=body, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 30) as res:
                elements = json.load(res)['elements']
            break
        except (OSError, ValueError) as e:
            errors.append(f'{url}: {e}')
    else:
        raise RuntimeError('Could not look up OSM IDs: ' + '; '.join(errors))

    resolved = {}
    for element in elements:
        number = str(element['id'])
        # A node and a way can share a number; prefer the one that's a toilet
        is_toilet = element.get('tags', {}).get('amenity') == 'toilets'
        if number not in resolved or is_toilet:
            resolved[number] = f"{element['type']}/{number}"
    return resolved
