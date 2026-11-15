"""Fetch bathroom rows from every source and normalize them.

Add a city by appending to REGIONS: the endpoint, which columns map onto the
shared bathroom fields, and how to build a stable id. OpenStreetMap is the
same query for every region; only the bounding box changes.
"""

import hashlib
import time
from dataclasses import dataclass, field

import requests

KIND_BATHROOM = 'bathroom'

REGIONS = {
    'nyc': {
        'source': 'nyc_opendata',
        'query': 'soda',
        'url': 'https://data.cityofnewyork.us/resource/i7jb-7jku.json',
        'page_size': 5000,
        # Rows outside this are bad geocodes, not nearby cities we meant to load.
        'bounds': (40.40, -74.30, 40.95, -73.65),
        'osm_bbox': (40.4774, -74.2591, 40.9176, -73.7004),
        # This dataset has no stable id.
        'id': 'hash',
        'fields': {
            'name': 'facility_name',
            'latitude': 'latitude',
            'longitude': 'longitude',
            'hours': 'hours_of_operation',
            'notes': ['additional_notes'],
            'status': 'status',
            'seasonal': 'open',
            'wheelchair': 'accessibility',
            'operator': 'operator',
            'location_type': 'location_type',
            'changing_table': 'changing_stations',
            'website': 'website',
            'restroom_type': 'restroom_type',
        },
    },
    'seattle': {
        'source': 'seattle_parks',
        'query': 'arcgis',
        'url': (
            'https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/'
            'Parks_Restrooms/FeatureServer/0/query'
        ),
        'page_size': 2000,
        'bounds': (47.30, -122.60, 47.90, -122.10),
        'osm_bbox': (47.4810, -122.4597, 47.7341, -122.2244),
        'id': ['GLOBALID', 'LOCATION_ID', 'PMAID', 'OBJECTID'],
        'inactive_field': 'LIFECYCLESTATUSTXT',
        'inactive_values': ['DE', 'DP', 'D', 'DM'],
        'closed_field': 'OPENTOPUBLIC',
        'closed_values': ['NO'],
        'location_type_default': 'Park',
        'fields': {
            'name': ['ALT_NAME', 'PARK'],
            'hours': 'HOURS',
            'notes': ['DESCRIPTION', 'NOTES_EXTERNAL'],
            'note_labels': [('RSNCLOSED', 'Closed')],
            'status': 'CURRENTSTATUS',
            'seasonal': 'SEASON',
            'operator': 'OWNERSHIP',
            'location_type': 'RESTROOMLOCATIONTYPE',
        },
    },
}

CITY_SOURCES = tuple(spec['source'] for spec in REGIONS.values())

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'

_SESSION = requests.Session()
_SESSION.headers['User-Agent'] = 'PoopyTime/1.0 (bathroom ingest)'


@dataclass
class FetchedRecord:
    source: str
    external_id: str
    name: str | None
    latitude: float
    longitude: float
    hours: str | None = None
    notes: str | None = None
    status: str | None = None
    seasonal: str | None = None
    wheelchair: str | None = None
    operator: str | None = None
    location_type: str | None = None
    changing_table: str | None = None
    fee: str | None = None
    website: str | None = None
    restroom_type: str | None = None
    raw: dict = field(default_factory=dict)
    active: bool = True
    kind: str = KIND_BATHROOM


def fetch_open_data(spec):
    records = []
    skipped = 0
    seen = {} if spec['id'] == 'hash' else set()
    fields = spec['fields']
    for raw, props in _rows(spec):
        latitude, longitude = _coordinates(spec, raw, props)
        if latitude is None or longitude is None or not in_bounds(latitude, longitude, spec['bounds']):
            skipped += 1
            continue
        name = _first(props, fields.get('name'))
        location_type = _first(props, fields.get('location_type')) or spec.get('location_type_default')
        external_id = _external_id(spec, props, name, location_type, latitude, longitude, seen)
        if not external_id:
            skipped += 1
            continue
        status = normalize_status(props.get(fields['status'])) if fields.get('status') else None
        if _value_in(props, spec.get('closed_field'), spec.get('closed_values')):
            status = 'closed'
        records.append(FetchedRecord(
            source=spec['source'],
            external_id=external_id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            hours=_first(props, fields.get('hours')),
            notes=_notes(props, fields),
            status=status,
            seasonal=_first(props, fields.get('seasonal')),
            wheelchair=normalize_wheelchair(props.get(fields['wheelchair'])) if fields.get('wheelchair') else None,
            operator=_first(props, fields.get('operator')),
            location_type=location_type,
            changing_table=_first(props, fields.get('changing_table')),
            fee=_first(props, fields.get('fee')),
            website=_first(props, fields.get('website')),
            restroom_type=_first(props, fields.get('restroom_type')),
            raw=props,
            active=not _value_in(props, spec.get('inactive_field'), spec.get('inactive_values')),
        ))
    print(f"{spec['source']}: {len(records)} rows, skipped {skipped} without usable coordinates")
    return records


def fetch_osm(bbox):
    south, west, north, east = bbox
    box = f'{south},{west},{north},{east}'
    query = f"""
[out:json][timeout:180];
(
  node["amenity"="toilets"]({box});
  way["amenity"="toilets"]({box});
  relation["amenity"="toilets"]({box});
);
out center tags;
"""
    elements = _post_overpass(query)
    records = []
    skipped = 0
    for element in elements:
        tags = element.get('tags') or {}
        latitude, longitude = _osm_coords(element)
        if latitude is None or longitude is None:
            skipped += 1
            continue
        access = (clean(tags.get('access')) or '').lower()
        records.append(FetchedRecord(
            source='osm',
            external_id=f"{element['type']}/{element['id']}",
            name=clean(tags.get('name')),
            latitude=latitude,
            longitude=longitude,
            hours=clean(tags.get('opening_hours')),
            notes=join_notes(tags.get('note'), tags.get('description')),
            wheelchair=normalize_wheelchair(tags.get('wheelchair')),
            operator=clean(tags.get('operator')),
            location_type=_osm_location_type(tags),
            changing_table=clean(tags.get('changing_table')),
            fee=clean(tags.get('fee')),
            restroom_type=_osm_restroom_type(tags),
            seasonal=clean(tags.get('seasonal')),
            raw={'type': element['type'], 'id': element['id'], 'tags': tags},
            active=access not in {'private', 'no'},
        ))
    print(f'osm {box}: {len(records)} rows, skipped {skipped} without coordinates')
    return records


def padded_bbox(records, default, pad=0.02):
    """Cover the default city window and any city-data points just outside it."""
    south, west, north, east = default
    for record in records:
        south = min(south, record.latitude - pad)
        west = min(west, record.longitude - pad)
        north = max(north, record.latitude + pad)
        east = max(east, record.longitude + pad)
    return (south, west, north, east)


def _rows(spec):
    if spec['query'] == 'soda':
        offset = 0
        while True:
            page = _get_json(spec['url'], params={'$limit': spec['page_size'], '$offset': offset})
            if not page:
                break
            for row in page:
                yield row, row
            if len(page) < spec['page_size']:
                break
            offset += spec['page_size']
        return
    if spec['query'] == 'arcgis':
        offset = 0
        while True:
            payload = _get_json(spec['url'], params={
                'where': '1=1',
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'geojson',
                'resultRecordCount': spec['page_size'],
                'resultOffset': offset,
            })
            page = payload.get('features') or []
            if not page:
                break
            for feature in page:
                yield feature, feature.get('properties') or {}
            if len(page) < spec['page_size']:
                break
            offset += spec['page_size']
        return
    raise ValueError(f"unknown query type {spec['query']}")


def _coordinates(spec, raw, props):
    if spec['query'] == 'arcgis':
        coordinates = (raw.get('geometry') or {}).get('coordinates') or [None, None]
        longitude = parse_coord(coordinates[0]) if coordinates else None
        latitude = parse_coord(coordinates[1]) if len(coordinates) > 1 else None
        return latitude, longitude
    fields = spec['fields']
    return (
        parse_coord(_first(props, fields.get('latitude'))),
        parse_coord(_first(props, fields.get('longitude'))),
    )


def _external_id(spec, props, name, location_type, latitude, longitude, seen):
    if spec['id'] == 'hash':
        base_id = stable_hash(name, location_type, f'{latitude:.5f}', f'{longitude:.5f}')
        seen[base_id] = seen.get(base_id, 0) + 1
        return base_id if seen[base_id] == 1 else f'{base_id}-{seen[base_id]}'
    external_id = None
    for column in spec['id']:
        value = props.get(column)
        external_id = str(value) if column == 'OBJECTID' and value is not None else clean(value)
        if external_id:
            break
    if not external_id or external_id in seen:
        object_id = props.get('OBJECTID')
        if external_id in seen and object_id is not None:
            external_id = f'{external_id}:{object_id}'
        else:
            return None
    seen.add(external_id)
    return external_id


def _first(props, columns):
    if not columns:
        return None
    names = columns if isinstance(columns, list) else [columns]
    for name in names:
        text = clean(props.get(name))
        if text:
            return text
    return None


def _notes(props, fields):
    parts = [props.get(column) for column in fields.get('notes') or []]
    for column, label in fields.get('note_labels') or []:
        text = clean(props.get(column))
        if text:
            parts.append(f'{label}: {text}')
    return join_notes(*parts)


def _value_in(props, field, values):
    if not field or not values:
        return False
    text = (clean(props.get(field)) or '').upper()
    return text in {value.upper() for value in values}


def _osm_coords(element):
    if element.get('type') == 'node':
        return element.get('lat'), element.get('lon')
    center = element.get('center') or {}
    return center.get('lat'), center.get('lon')


def _osm_location_type(tags):
    indoor = (clean(tags.get('indoor')) or '').lower()
    if indoor == 'yes':
        return 'indoor'
    if indoor == 'no':
        return 'outdoor'
    return None


def _osm_restroom_type(tags):
    parts = [key for key in ('unisex', 'male', 'female') if (clean(tags.get(key)) or '').lower() == 'yes']
    return ', '.join(parts) or None


def _get_json(url, params=None):
    response = _SESSION.get(url, params=params, timeout=(10, 120))
    response.raise_for_status()
    return response.json()


def _post_overpass(query, attempts=3):
    last_error = None
    for attempt in range(attempts):
        response = _SESSION.post(OVERPASS_URL, data={'data': query}, timeout=(10, 240))
        if response.status_code in {429, 502, 503, 504}:
            last_error = RuntimeError(f'overpass HTTP {response.status_code}')
            time.sleep(15 * (attempt + 1))
            continue
        response.raise_for_status()
        payload = response.json()
        if 'elements' not in payload:
            raise RuntimeError(payload.get('remark') or 'overpass returned no elements')
        return payload['elements']
    raise last_error or RuntimeError('overpass failed')


def clean(value):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text or None


def parse_coord(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def in_bounds(latitude, longitude, bounds):
    south, west, north, east = bounds
    return south <= latitude <= north and west <= longitude <= east


def normalize_status(value):
    text = clean(value)
    if not text:
        return None
    lowered = text.lower()
    if 'limited' in lowered or 'partial' in lowered:
        return 'limited'
    if lowered in {'operational', 'open', 'yes'} or lowered.startswith('open'):
        return 'open'
    if 'closed' in lowered or 'not operational' in lowered or 'decommission' in lowered:
        return 'closed'
    return 'unknown'


def normalize_wheelchair(value):
    text = clean(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in {'yes', 'true', 'fully accessible', 'accessible', 'ada accessible'}:
        return 'yes'
    if lowered in {'no', 'false', 'not accessible', 'none'}:
        return 'no'
    if 'partial' in lowered or 'limited' in lowered:
        return 'limited'
    return None


def join_notes(*parts):
    cleaned = []
    for part in parts:
        text = clean(part)
        if text and text not in cleaned:
            cleaned.append(text)
    return '\n'.join(cleaned) or None


def stable_hash(*parts):
    raw = '|'.join('' if part is None else str(part).strip().lower() for part in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
