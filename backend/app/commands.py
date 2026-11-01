import click

from app import db
from app.models.bathroomDB import Bathroom
from app.services import geocoding, osm_toilets

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
            for key, value in fields.items():
                setattr(bathroom, key, value)

        south, west, north, east = bounds
        gone = Bathroom.query.filter(
            Bathroom.source == 'osm',
            Bathroom.latitude.between(south, north),
            Bathroom.longitude.between(west, east),
            Bathroom.osm_id.notin_(seen),
        ).all()
        for bathroom in gone:
            db.session.delete(bathroom)

        db.session.commit()
        click.echo(f'Added {added}, updated {updated}, removed {len(gone)}, '
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
