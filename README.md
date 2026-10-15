# Poopy Time

Monorepo with a Flask API, a React web app, and an Expo (React Native) mobile app for iOS and Android. Layout mirrors `set-up-app`.

```
poopy-time/
├── backend/             Flask API (SQLAlchemy, JWT auth, Flask-Migrate)
├── frontend-app/        React web app (Create React App)
├── poopy-time-mobile/   Expo app → iOS + Android (EAS Build)
├── Dockerfile           Backend image (built from repo root)
├── entrypoint.sh        Runs migrations, then Gunicorn
├── Procfile             Alternative process definition
└── railway.json         Railway config for the backend service
```

## Backend (Flask)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp env.template .env                 # optional; defaults to local SQLite
flask db init && flask db migrate -m "init" && flask db upgrade
flask run --host=0.0.0.0 --port=5000
```

(`make setup` / `make run` do the same on macOS/Linux.)

Endpoints:

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Health check |
| POST | `/auth/signup` | `{ email, password, display_name? }` → `{ token, user }` |
| POST | `/auth/login` | `{ email, password }` → `{ token, user }` |
| GET | `/auth/me` | Requires `Authorization: Bearer <token>` |

Add new features as a model in `app/models/`, a blueprint in `app/routes/` (registered in `routes/__init__.py`), and any business logic in `app/services/`. Use `@token_required` from `routes/shared.py` for authenticated routes.

## Web (frontend-app)

```bash
cd frontend-app
cp .env.example .env
npm install
npm start          # http://localhost:3000
```

Deploys to Railway via its `Dockerfile` (set Root Directory to `frontend-app`) or Cloudflare via `wrangler.toml`.

## Mobile (poopy-time-mobile)

```bash
cd poopy-time-mobile
cp .env.example .env   # point at your computer's LAN IP so the phone can reach the API
npm install
npx expo start         # Expo Go: use `npm run start:go`
```

Native builds: `npm run android` / `npm run ios` (iOS requires macOS), or EAS: `npx eas init` then `npm run build:dev:ios` / `npm run build:dev:android`. Update `bundleIdentifier` / `package` in `app.json` (currently `com.poopytime.app`) and the API URLs in `eas.json` before your first build.

## Deploying the backend (Railway)

The root `Dockerfile` + `railway.json` build the backend. Set `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, and `CORS_ORIGINS` on the service. `entrypoint.sh` creates and applies migrations on start.
