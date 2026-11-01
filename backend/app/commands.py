import click

from app import db
from app.models.bathroomDB import Bathroom

# (name, lat offset, lng offset, open_hour, close_hour, is_accessible)
SAMPLE_BATHROOMS = [
    ('Sample Cafe Restroom', 0.0025, 0.0018, 8, 22, True),
    ('Sample Library Restroom', -0.0032, -0.0036, 9, 20, True),
    ('Sample Park Restroom', 0.0041, -0.0045, None, None, False),
    ('Sample Station Restroom', -0.0060, 0.0052, 5, 24, True),
]


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
