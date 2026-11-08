import math

import click

from app import db
from app.models.bathroomDB import Bathroom
from app.services import geocoding, osm_toilets, seattle_parks

# Two records this close together are treated as the same restroom
MATCH_METERS = 30

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

        added = updated = skipped = 0
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
            if bathroom.city_id:
                # Gone from OSM but still listed by Seattle Parks
                bathroom.source, bathroom.osm_id = 'seattle_parks', None
                kept += 1
            else:
                db.session.delete(bathroom)

        db.session.commit()
        click.echo(f'Added {added}, updated {updated}, removed {len(gone) - kept}, '
                   f'skipped {skipped} (private or no location).')

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
            if hours:
                bathroom.open_hour, bathroom.close_hour, bathroom.hours_note = hours
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
