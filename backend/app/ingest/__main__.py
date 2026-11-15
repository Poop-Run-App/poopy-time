import argparse

from app import create_app
from app.ingest.pipeline import run
from app.ingest.sources import REGIONS


def main():
    parser = argparse.ArgumentParser(prog='python -m app.ingest')
    parser.add_argument('command', choices=('init', 'update'))
    parser.add_argument('--region', choices=(*REGIONS, 'all'), default='all')
    parser.add_argument('--force', action='store_true', help='init only: wipe existing bathroom rows first.')
    parser.add_argument(
        '--allow-remote',
        action='store_true',
        help='Allow a non-SQLite DATABASE_URL. Local runs should leave this off.',
    )
    args = parser.parse_args()
    with create_app().app_context():
        run(args.command, args.region, force=args.force, allow_remote=args.allow_remote)


main()
