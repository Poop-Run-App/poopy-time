import math

import click

from app import db
from app.models.bathroomDB import Bathroom
from app.services import geocoding, osm_toilets, seattle_parks, tracking_sheet

# Two records this close together are treated as the same restroom
MATCH_METERS = 30
# A sheet row matches an existing bathroom with the same name this close by
SHEET_MATCH_METERS = 15
SHEET_CLOSED_REASON = 'Reported closed'

# (name, lat offset, lng offset, open_hour, close_hour, is_accessible)
SAMPLE_BATHROOMS = [
    ('Sample Cafe Restroom', 0.0025, 0.0018, 8, 22, True),
    ('Sample Library Restroom', -0.0032, -0.0036, 9, 20, True),
    ('Sample Park Restroom', 0.0041, -0.0045, None, None, False),
    ('Sample Station Restroom', -0.0060, 0.0052, 5, 24, True),
]


def _parse_area(city, bbox):
    """(south, west, north, east) from --city or --bbox."""
    if bool(city) == bool(bbox):
        raise click.UsageError('Give exactly one of --city or --bbox.')
    if city:
        return osm_toilets.CITY_BOUNDS[city]
    try:
        bounds = tuple(float(v) for v in bbox.split(','))
    except ValueError:
        bounds = ()
    if len(bounds) != 4:
        raise click.UsageError('--bbox must be four numbers: south,west,north,east')
    return bounds


def _meters_between(lat1, lng1, lat2, lng2):
    """Approximate distance; accurate enough at matching range."""
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371000 * math.hypot(x, y)


def _nearest_within(lat, lng, meters, *filters):
    """Closest bathroom matching filters within `meters`, or None."""
    d_lat = meters / 111000
    d_lng = meters / (111000 * math.cos(math.radians(lat)))
    candidates = Bathroom.query.filter(
        Bathroom.latitude.between(lat - d_lat, lat + d_lat),
        Bathroom.longitude.between(lng - d_lng, lng + d_lng),
        *filters,
    ).all()
    scored = [(_meters_between(lat, lng, b.latitude, b.longitude), b) for b in candidates]
    scored = [(d, b) for d, b in scored if d <= meters]
    return min(scored, key=lambda pair: pair[0])[1] if scored else None


def register_commands(app):
    @app.cli.command('seed-bathrooms')
    @click.option('--lat', type=float, required=True, help='Latitude to place sample bathrooms around.')
    @click.option('--lng', type=float, required=True, help='Longitude to place sample bathrooms around.')
    def seed_bathrooms(lat, lng):
        """Add sample bathrooms near a point, for local development."""
        for name, d_lat, d_lng, open_hour, close_hour, accessible in SAMPLE_BATHROOMS:
            db.session.add(Bathroom(
                name=name,
                latitude=lat + d_lat,
                longitude=lng + d_lng,
                open_hour=open_hour,
                close_hour=close_hour,
                is_accessible=accessible,
            ))
        db.session.commit()
        click.echo(f'Added {len(SAMPLE_BATHROOMS)} sample bathrooms near {lat}, {lng}.')

    @app.cli.command('import-osm-toilets')
    @click.option('--city', type=click.Choice(sorted(osm_toilets.CITY_BOUNDS)), help='A known city area.')
    @click.option('--bbox', help='Custom area as "south,west,north,east".')
    def import_osm_toilets(city, bbox):
        """Import public toilets from OpenStreetMap. Safe to re-run: updates
        existing imports and removes ones no longer in OSM."""
        bounds = _parse_area(city, bbox)

        click.echo('Downloading toilets from OpenStreetMap...')
        try:
            elements, places = osm_toilets.fetch_toilets(bounds, log=click.echo)
        except RuntimeError as e:
            raise click.ClickException(str(e))

        added = updated = skipped = kept_curated = 0
        seen = set()
        for element in elements:
            fields = osm_toilets.to_bathroom_fields(element, places)
            if not fields:
                skipped += 1
                continue
            seen.add(fields['osm_id'])
            bathroom = Bathroom.query.filter_by(osm_id=fields['osm_id']).first()
            if not bathroom:
                # A Seattle Parks restroom that OSM has now mapped too
                bathroom = _nearest_within(
                    fields['latitude'], fields['longitude'], MATCH_METERS,
                    Bathroom.source == 'seattle_parks', Bathroom.osm_id.is_(None))
            if bathroom and (bathroom.curated or bathroom.source == 'sheet'):
                # The team's sheet owns this one's details
                kept_curated += 1
                continue
            if bathroom:
                updated += 1
            else:
                bathroom = Bathroom()
                db.session.add(bathroom)
                added += 1
            # OSM rarely has addresses for toilets; keep one filled in by
            # fill-addresses (or by hand) rather than blanking it
            if not fields['address'] and bathroom.address:
                del fields['address']
            # Seattle Parks keeps its own hours; they're better than OSM's
            if bathroom.city_id:
                for key in ('open_hour', 'close_hour', 'hours_note'):
                    del fields[key]
            for key, value in fields.items():
                setattr(bathroom, key, value)

        south, west, north, east = bounds
        gone = Bathroom.query.filter(
            Bathroom.source == 'osm',
            Bathroom.latitude.between(south, north),
            Bathroom.longitude.between(west, east),
            Bathroom.osm_id.notin_(seen),
        ).all()
        kept = 0
        for bathroom in gone:
            if bathroom.curated:
                # Gone from OSM but the team still tracks it
                bathroom.source, bathroom.osm_id = 'sheet', None
                kept += 1
            elif bathroom.city_id:
                # Gone from OSM but still listed by Seattle Parks
                bathroom.source, bathroom.osm_id = 'seattle_parks', None
                kept += 1
            else:
                db.session.delete(bathroom)

        db.session.commit()
        click.echo(f'Added {added}, updated {updated}, removed {len(gone) - kept}, '
                   f'skipped {skipped} (private or no location), '
                   f'left {kept_curated} team-edited bathrooms unchanged.')

    @app.cli.command('fill-addresses')
    @click.option('--city', type=click.Choice(sorted(osm_toilets.CITY_BOUNDS)), help='A known city area.')
    @click.option('--bbox', help='Custom area as "south,west,north,east".')
    def fill_addresses(city, bbox):
        """Look up a street address for bathrooms that have none, using
        OpenStreetMap's Nominatim (one request per second)."""
        south, west, north, east = _parse_area(city, bbox)
        missing = Bathroom.query.filter(
            Bathroom.address.is_(None),
            Bathroom.latitude.between(south, north),
            Bathroom.longitude.between(west, east),
        ).order_by(Bathroom.id).all()
        click.echo(f'{len(missing)} bathrooms without an address, about {len(missing) * 1.1 / 60:.0f} min...')

        filled = not_found = failed = 0
        for i, bathroom in enumerate(missing, start=1):
            try:
                address = geocoding.reverse_geocode(bathroom.latitude, bathroom.longitude)
            except (OSError, ValueError) as e:
                failed += 1
                click.echo(f'  #{bathroom.id}: lookup failed ({e})')
                continue
            if address:
                bathroom.address = address[:255]
                filled += 1
            else:
                not_found += 1
            if i % 25 == 0:
                db.session.commit()
                click.echo(f'  {i}/{len(missing)}')

        db.session.commit()
        click.echo(f'Filled {filled}, no street found for {not_found}, failed {failed}.')

    @app.cli.command('import-seattle-parks')
    def import_seattle_parks():
        """Add hours and open/closed status from Seattle Parks' public restrooms,
        and add the ones not already in the database. Safe to re-run."""
        click.echo('Downloading Seattle Parks restrooms...')
        try:
            features = seattle_parks.fetch_restrooms()
        except (OSError, ValueError) as e:
            raise click.ClickException(f'Could not download Seattle Parks data: {e}')

        matched = added = updated = 0
        seen = set()
        for feature in features:
            props = feature['properties']
            if not seattle_parks.is_public(props) or not feature.get('geometry'):
                continue
            city_id = props['AMWOID']
            lng, lat = feature['geometry']['coordinates'][:2]
            seen.add(city_id)

            bathroom = Bathroom.query.filter_by(city_id=city_id).first()
            if bathroom:
                updated += 1
            else:
                bathroom = _nearest_within(lat, lng, MATCH_METERS, Bathroom.city_id.is_(None))
                if bathroom:
                    matched += 1
                else:
                    bathroom = Bathroom(
                        name=seattle_parks.display_name(props),
                        latitude=lat,
                        longitude=lng,
                        is_accessible=False,
                        notes='Portable toilet' if props.get('SANICAN') == 'YES' else None,
                        source='seattle_parks',
                    )
                    db.session.add(bathroom)
                    added += 1
                bathroom.city_id = city_id
            if bathroom.source == 'seattle_parks':
                bathroom.name = seattle_parks.display_name(props)

            hours = seattle_parks.parse_hours(props)
            if hours and not bathroom.curated:
                bathroom.open_hour, bathroom.close_hour, bathroom.hours_note = hours
            # A closure the team reported stands until the team clears it
            if bathroom.status_reason != SHEET_CLOSED_REASON:
                bathroom.status, bathroom.status_reason = seattle_parks.parse_status(props)
            db.session.flush()

        removed = unlinked = 0
        for bathroom in Bathroom.query.filter(Bathroom.city_id.isnot(None), Bathroom.city_id.notin_(seen)):
            if bathroom.source == 'seattle_parks':
                db.session.delete(bathroom)
                removed += 1
            else:
                bathroom.city_id = bathroom.status = bathroom.status_reason = None
                unlinked += 1

        db.session.commit()
        click.echo(f'Matched {matched} to existing bathrooms, added {added}, updated {updated}, '
                   f'removed {removed}, unlinked {unlinked}.')

    @app.cli.command('import-sheet')
    @click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
    @click.option('--dry-run', is_flag=True, help='Report what would change without saving.')
    def import_sheet(csv_path, dry_run):
        """Add or update bathrooms from a team tracking sheet exported as CSV.

        Rows match existing bathrooms by OSM ID, else by the same name within
        15 m. Bathrooms whose details the sheet changes are marked team-edited,
        so the OSM and Seattle Parks imports stop overwriting them. Blank
        address, hours or gender cells don't erase what's already known."""
        try:
            rows = tracking_sheet.read_rows(csv_path)
        except tracking_sheet.SheetError as e:
            raise click.ClickException(str(e))
        click.echo(f'{len(rows)} rows. Looking up OSM IDs...')
        try:
            osm_ids = tracking_sheet.resolve_osm_types(r['osm_number'] for r in rows if r['osm_number'])
        except RuntimeError as e:
            raise click.ClickException(str(e))

        added = changed = unchanged = 0
        unresolved = sum(1 for r in rows if r['osm_number'] and r['osm_number'] not in osm_ids)
        claimed = set()  # each bathroom matches at most one row per run
        for row in rows:
            osm_id = osm_ids.get(row['osm_number'])
            bathroom = Bathroom.query.filter_by(osm_id=osm_id).first() if osm_id else None
            if bathroom and bathroom.id in claimed:
                bathroom = None
            if not bathroom:
                bathroom = _nearest_within(row['latitude'], row['longitude'], SHEET_MATCH_METERS,
                                           db.func.lower(Bathroom.name) == row['name'].lower(),
                                           Bathroom.id.notin_(claimed))
            if bathroom:
                claimed.add(bathroom.id)

            if not bathroom:
                taken = osm_id and Bathroom.query.filter_by(osm_id=osm_id).first()
                bathroom = Bathroom(
                    name=row['name'], address=row['address'],
                    latitude=row['latitude'], longitude=row['longitude'],
                    open_hour=row['open_hour'], close_hour=row['close_hour'],
                    # Blank hours mean unknown; with no note, null hours read as 24 hours
                    hours_note=None if row['open_hour'] is not None else 'Hours unknown',
                    is_accessible=row['is_accessible'], gender=row['gender'],
                    status='closed' if row['closed'] else None,
                    status_reason=SHEET_CLOSED_REASON if row['closed'] else None,
                    source='sheet', curated=True,
                    osm_id=None if taken else osm_id,
                )
                db.session.add(bathroom)
                db.session.flush()
                claimed.add(bathroom.id)
                added += 1
                continue

            updates = {'name': row['name'], 'is_accessible': row['is_accessible']}
            for key in ('address', 'gender'):
                if row[key]:
                    updates[key] = row[key]
            if row['open_hour'] is not None:
                updates['open_hour'], updates['close_hour'] = row['open_hour'], row['close_hour']
            elif bathroom.open_hour is None and bathroom.hours_note is None:
                updates['hours_note'] = 'Hours unknown'
            if _meters_between(row['latitude'], row['longitude'], bathroom.latitude, bathroom.longitude) > 0.5:
                updates['latitude'], updates['longitude'] = row['latitude'], row['longitude']
            if row['closed'] and bathroom.status != 'closed':
                updates['status'], updates['status_reason'] = 'closed', SHEET_CLOSED_REASON
            elif not row['closed'] and bathroom.status_reason == SHEET_CLOSED_REASON:
                updates['status'], updates['status_reason'] = None, None

            diff = {k: v for k, v in updates.items() if getattr(bathroom, k) != v}
            if not diff:
                unchanged += 1
                continue
            if 'open_hour' in diff or 'close_hour' in diff:
                diff['hours_note'] = None  # the source's wording no longer matches
            for key, value in diff.items():
                setattr(bathroom, key, value)
            bathroom.curated = True
            changed += 1

        if dry_run:
            db.session.rollback()
            click.echo('Dry run, nothing saved.')
        else:
            db.session.commit()
        click.echo(f'Added {added}, updated {changed}, unchanged {unchanged}. '
                   f'{unresolved} OSM IDs not found in OSM (matched by name and location instead).')
