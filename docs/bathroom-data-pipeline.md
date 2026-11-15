# Bathroom data pipeline

How bathroom records get into the database. Water fountains are a later step and are not loaded yet.

## Where the data lives

One table, `bathrooms` ([backend/app/models/bathroomDB.py](../backend/app/models/bathroomDB.py)). The bathroom API (`/bathrooms/nearby`, `/bathrooms/in-view`) and the Emergency map read from it.

Each row has a display name, latitude and longitude, hours as `open_hour` / `close_hour` (0-24, 17.5 = 5:30pm, overnight ranges allowed) plus `hours_note` for wording that isn't a single daily range, `is_accessible`, `gender`, `notes`, `status` / `status_reason`, and an optional address.

How a row is linked to its sources:

- `source`: where it came from: `osm`, `seattle_parks`, `nyc_opendata`, `sheet`, or `user`
- `osm_id`: OpenStreetMap id such as `node/123`, set on any row OSM has
- `city_id`: the city dataset's id, set on any row a city lists. A Seattle Parks asset id (e.g. `RESTROOM-SCCS`), or `nyc:` plus a hash of the facility name, location type, and position for NYC (that dataset has no stable id)
- `curated`: the team edited it through the tracking sheet

There is no city column. Latitude and longitude say where a bathroom is.

## Sources

- **OpenStreetMap:** Overpass `amenity=toilets` in a city's bounding box (`osm_toilets.CITY_BOUNDS`: `seattle`, `nyc`) or any `--bbox`. Unnamed toilets are named after the park they're in. Private toilets are skipped.
- **Seattle Parks:** the City's [Park Restrooms](https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/Parks_Restrooms/FeatureServer/0) layer. Only public, active restrooms. Hours like `7AM - 7/9PM` become a range with a note; closures keep their reason.
- **NYC Open Data:** [Public Restrooms](https://data.cityofnewyork.us/City-Government/Public-Restrooms/i7jb-7jku) (`i7jb-7jku`). A single daily range like `8am-4pm` becomes hours; weekly schedules and phrases like `7am - dusk` stay as `hours_note`. Also maps accessibility, restroom type (to `gender`), changing tables and notes, and status (`Not Operational`, `Closed for Construction`, and not-yet-open sites show as closed).
- **Team tracking sheet:** one Google Sheet per state, one tab per city, exported as CSV and loaded with `flask import-sheet`.

Code is in [backend/app/services/](../backend/app/services/) (`osm_toilets.py`, `seattle_parks.py`, `nyc_restrooms.py`, `tracking_sheet.py`, `geocoding.py`). The commands are in [backend/app/commands.py](../backend/app/commands.py).

## Merge rules

- A city restroom and an OSM toilet within 30 meters are the same bathroom.
- City data wins over OSM. On a city-matched bathroom the city's name, coordinates, and hours are kept no matter which import runs last. For NYC, accessibility is the city's too, and NYC's restroom type and notes win when NYC has them. OSM fills in what the city doesn't report (gender and notes for Seattle, address everywhere).
- The team sheet wins over both. Once a row is `curated`, the OSM and city imports leave its details alone. A closure the team reported stays until the team clears it.
- When a city stops listing a restroom, a city-only row is deleted and a row OSM also has is unlinked from the city. When OSM drops a toilet, a city-matched row goes back to the city's source instead of being deleted.

## Commands

From `backend`, with the virtualenv active:

```bash
flask db upgrade
flask import-osm-toilets --city seattle
flask import-seattle-parks
flask import-osm-toilets --city nyc
flask import-nyc-restrooms
flask import-sheet path/to/sheet.csv     # --dry-run to preview
flask fill-addresses --city nyc          # optional, about 1 lookup per second
```

Every import is safe to re-run. Run the OSM import before the city import for a new area so the city import can match against OSM; after that, order doesn't matter. Overpass is often busy, and the OSM import retries with a mirror.

The commands write to whatever `DATABASE_URL` points at: local SQLite (`backend/instance/app.db`, gitignored) when it is blank, or Railway when it is set. Imports don't run from `entrypoint.sh`; deploys only run `flask db upgrade`.

## Local test

On 15 Nov 2026, against local SQLite at migration `0d9d5b11f901`, the four imports in the order above loaded:

- OSM Seattle: 263 toilets. Seattle Parks: 127 public restrooms; 103 matched an OSM toilet and 24 were new.
- OSM NYC: 936 toilets. NYC Open Data: 1,100 restrooms; 477 matched an OSM toilet and 623 were new.
- 1,846 bathrooms total, 1,227 linked to a city dataset.

Running all four again changed no rows. Running the Seattle OSM import by itself afterward also changed no rows, so OSM doesn't overwrite city names, coordinates, or hours. Example: Rockaway Beach 07b keeps NYC's position and `8am-4pm, Open later seasonally` while also carrying its OSM id.

## Water fountains later

Not loaded. A later step can add Overpass `amenity=drinking_water` and any city fountain datasets using the same importer pattern.
