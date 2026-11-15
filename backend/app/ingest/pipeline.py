"""Write fetched rows to source_records, then rebuild merged places."""

import math
from datetime import datetime, timezone

from app import db
from app.ingest.sources import CITY_SOURCES, KIND_BATHROOM, REGIONS, fetch_open_data, fetch_osm, padded_bbox
from app.models.place import Place, SourceRecord

MATCH_METERS = 30
FALLBACK_NAME = 'Public restroom'
MERGE_FIELDS = (
    'hours',
    'notes',
    'status',
    'seasonal',
    'wheelchair',
    'operator',
    'location_type',
    'changing_table',
    'fee',
    'website',
    'restroom_type',
)
RECORD_FIELDS = ('kind', 'name', 'latitude', 'longitude', *MERGE_FIELDS, 'raw', 'active')
# ~111m. 30m matches only need the surrounding cells.
_CELL = 0.001


def run(command, region, force=False, allow_remote=False):
    _assert_database(allow_remote)
    if command == 'init':
        existing = Place.query.filter_by(kind=KIND_BATHROOM).count() + SourceRecord.query.filter_by(kind=KIND_BATHROOM).count()
        if existing and not force:
            raise SystemExit(
                f'{existing} bathroom rows already exist. Re-run with --force to wipe them, '
                'or use python -m app.ingest update.'
            )
        if existing:
            SourceRecord.query.filter_by(kind=KIND_BATHROOM).delete(synchronize_session=False)
            Place.query.filter_by(kind=KIND_BATHROOM).delete(synchronize_session=False)
            print('wiped bathroom places and source records')
    _load(region)


def _load(region):
    selected = list(REGIONS) if region == 'all' else [region]
    fetched = []
    osm_boxes = []
    replaced_sources = set()
    for name in selected:
        spec = REGIONS[name]
        print(f'fetching {name} open data')
        city_rows = fetch_open_data(spec)
        if not city_rows:
            raise RuntimeError(f'{name} open data returned no rows; database was not changed')
        bbox = padded_bbox(city_rows, spec['osm_bbox'])
        print(f'fetching osm for {name}')
        osm_rows = fetch_osm(bbox)
        if not osm_rows:
            raise RuntimeError(f'osm returned no rows for {name}; database was not changed')
        fetched.extend(city_rows)
        fetched.extend(osm_rows)
        osm_boxes.append(bbox)
        replaced_sources.add(spec['source'])

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = {
        (row.source, row.external_id): row
        for row in SourceRecord.query.filter_by(kind=KIND_BATHROOM)
    }
    seen = set()
    for record in fetched:
        key = (record.source, record.external_id)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            row = SourceRecord(source=record.source, external_id=record.external_id)
            db.session.add(row)
            existing[key] = row
        for name in RECORD_FIELDS:
            setattr(row, name, getattr(record, name))
        row.fetched_at = now

    for key, row in existing.items():
        if key in seen:
            continue
        if row.source in replaced_sources or (row.source == 'osm' and _in_any_box(row, osm_boxes)):
            row.active = False

    db.session.flush()
    _rematch(list(existing.values()))
    db.session.commit()
    _print_summary()


def _rematch(source_rows):
    """City rows own places; OSM fills blanks or stands alone."""
    places = {place.owner_key: place for place in Place.query.filter_by(kind=KIND_BATHROOM)}
    city_rows = [row for row in source_rows if row.active and row.source in CITY_SOURCES]
    osm_rows = sorted(
        (row for row in source_rows if row.active and row.source == 'osm'),
        key=lambda row: row.external_id,
    )

    index = {}
    for row in city_rows:
        place = _own_place(places, row)
        index.setdefault(_cell(place.latitude, place.longitude), []).append(place)

    for row in osm_rows:
        nearest, distance = _nearest(index, row.latitude, row.longitude)
        if nearest is None or distance > MATCH_METERS:
            _own_place(places, row)
            continue
        row.place_id = nearest.id
        row.match_distance_m = round(distance, 2)
        if nearest.display_name == FALLBACK_NAME and row.name:
            nearest.display_name = row.name
        for name in MERGE_FIELDS:
            if not getattr(nearest, name) and getattr(row, name):
                setattr(nearest, name, getattr(row, name))

    owners = {
        _owner_key(row)
        for row in source_rows
        if row.active and row.place_id is not None and row.match_distance_m is None
    }
    for place in places.values():
        if place.owner_key not in owners:
            place.active = False
        elif not place.status:
            place.status = 'unknown'


def _own_place(places, row):
    key = _owner_key(row)
    place = places.get(key)
    if place is None:
        place = Place(kind=KIND_BATHROOM, owner_key=key)
        db.session.add(place)
        places[key] = place
    place.display_name = row.name or FALLBACK_NAME
    place.latitude = row.latitude
    place.longitude = row.longitude
    place.primary_source = row.source
    place.active = True
    for name in MERGE_FIELDS:
        setattr(place, name, getattr(row, name))
    db.session.flush()
    row.place_id = place.id
    row.match_distance_m = None
    return place


def _owner_key(row):
    return f'{row.source}:{row.external_id}'


def _nearest(index, latitude, longitude):
    cx, cy = _cell(latitude, longitude)
    best = None
    best_distance = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for place in index.get((cx + dx, cy + dy), []):
                distance = _haversine_m(latitude, longitude, place.latitude, place.longitude)
                if best_distance is None or distance < best_distance:
                    best = place
                    best_distance = distance
    return best, best_distance


def _cell(latitude, longitude):
    return (int(latitude / _CELL), int(longitude / _CELL))


def _haversine_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def _in_any_box(row, boxes):
    return any(
        south <= row.latitude <= north and west <= row.longitude <= east
        for south, west, north, east in boxes
    )


def _assert_database(allow_remote):
    uri = db.engine.url
    if uri.get_backend_name() == 'sqlite':
        print(f'database: sqlite {uri.database}')
        return
    if allow_remote:
        print(f'database: {uri.get_backend_name()} {uri.host}/{uri.database}')
        return
    raise SystemExit(
        'Refusing to write to a non-SQLite database. Pass --allow-remote after the local run looks right.'
    )


def _print_summary():
    print('places:')
    for source, count in _active_counts(Place, Place.primary_source):
        print(f'  {source}: {count} active')
    print(f'  inactive: {Place.query.filter_by(kind=KIND_BATHROOM, active=False).count()}')
    print('source records:')
    for source, count in _active_counts(SourceRecord, SourceRecord.source):
        print(f'  {source}: {count} active')
    attached = SourceRecord.query.filter(
        SourceRecord.kind == KIND_BATHROOM,
        SourceRecord.source == 'osm',
        SourceRecord.active.is_(True),
        SourceRecord.match_distance_m.isnot(None),
    ).count()
    print(f'  osm attached to a city place: {attached}')


def _active_counts(model, column):
    rows = (
        db.session.query(column, db.func.count())
        .filter(model.kind == KIND_BATHROOM, model.active.is_(True))
        .group_by(column)
        .all()
    )
    return sorted(rows)
