import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, AttributionControl, ZoomControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { snapToWalkable, metersToMiles } from '../../data/routes';
import { pathLengthMeters } from '../../utils/geometry';
import './route.css';

// Used when the browser can't or won't share a location
const FALLBACK_LOCATION = { lat: 40.7128, lng: -74.006 };

// Strokes shorter than this are taps, not drawings
const MIN_STROKE_METERS = 15;
// Skip pointer moves smaller than this many screen pixels
const MIN_STEP_PIXELS = 3;

const STYLE = {
  drawing: { color: '#2b1d12', weight: 4, opacity: 0.8, interactive: false },
  // The raw sketch: solid while it's being matched, a faint dashed ghost once the route is back
  sketch: { color: '#2b1d12', weight: 3, opacity: 0.7, interactive: false },
  sketchGhost: { color: '#7a6a5c', weight: 2, opacity: 0.7, dashArray: '2 6', interactive: false },
  casing: { color: '#ffffff', weight: 9, opacity: 0.95, lineCap: 'round', lineJoin: 'round', interactive: false },
  route: { color: '#8b5e3c', weight: 5, lineCap: 'round', lineJoin: 'round', interactive: false },
  gap: { color: '#c0392b', weight: 4, dashArray: '6 8', interactive: false },
};

// Lets the user trace a line on the map with a finger or mouse. While active,
// dragging draws instead of panning; each finished stroke goes to onStroke as
// [[lat, lng], ...].
function DrawLayer({ active, onStroke }) {
  const map = useMap();
  const onStrokeRef = useRef(onStroke);
  useEffect(() => { onStrokeRef.current = onStroke; });

  useEffect(() => {
    if (!active) return undefined;
    const el = map.getContainer();
    const previousTouchAction = el.style.touchAction;
    el.style.touchAction = 'none';
    map.dragging.disable();
    map.doubleClickZoom.disable();

    let stroke = null; // { id, points, last (screen point), line }

    const finish = (commit) => {
      if (!stroke) return;
      const { id, points, line } = stroke;
      stroke = null;
      line.remove();
      if (el.hasPointerCapture && el.hasPointerCapture(id)) el.releasePointerCapture(id);
      if (commit && pathLengthMeters(points) >= MIN_STROKE_METERS) onStrokeRef.current(points);
    };

    const onDown = (e) => {
      if (stroke) return;  // a second finger is pinch-zooming, not drawing
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (e.target.closest && e.target.closest('.leaflet-control')) return;
      e.preventDefault();
      const latlng = map.mouseEventToLatLng(e);
      stroke = {
        id: e.pointerId,
        points: [[latlng.lat, latlng.lng]],
        last: map.mouseEventToContainerPoint(e),
        line: L.polyline([latlng], STYLE.drawing).addTo(map),
      };
      el.setPointerCapture(e.pointerId);
    };
    const onMove = (e) => {
      if (!stroke || e.pointerId !== stroke.id) return;
      const point = map.mouseEventToContainerPoint(e);
      if (point.distanceTo(stroke.last) < MIN_STEP_PIXELS) return;
      const latlng = map.mouseEventToLatLng(e);
      stroke.points.push([latlng.lat, latlng.lng]);
      stroke.last = point;
      stroke.line.addLatLng(latlng);
    };
    const onUp = (e) => { if (stroke && e.pointerId === stroke.id) finish(true); };
    const onCancel = (e) => { if (stroke && e.pointerId === stroke.id) finish(false); };

    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onCancel);

    return () => {
      finish(false);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onCancel);
      el.style.touchAction = previousTouchAction;
      try {
        map.dragging.enable();
        map.doubleClickZoom.enable();
      } catch (err) {
        // The map was already torn down (leaving the page)
      }
    };
  }, [map, active]);

  return null;
}

function formatMiles(meters) {
  const miles = metersToMiles(meters);
  return `${miles >= 1 ? miles.toFixed(1) : miles.toFixed(2)} ${miles === 1 ? 'mile' : 'miles'}`;
}

export default function RoutePlanner() {
  const [location, setLocation] = useState(null);
  const [locationError, setLocationError] = useState('');
  const [drawing, setDrawing] = useState(false);
  // Everything the user has drawn, one array of [lat, lng] per stroke
  const [strokes, setStrokes] = useState([]);
  // The drawing moved onto walkable paths
  const [route, setRoute] = useState(null);
  const [snapping, setSnapping] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!navigator.geolocation) {
      setLocationError('Location unavailable');
      setLocation(FALLBACK_LOCATION);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => {
        setLocationError('Location unavailable');
        setLocation(FALLBACK_LOCATION);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }, []);

  // The sketch is every stroke joined end to start, so the gap between two
  // strokes gets routed along walkable paths too
  const sketch = useMemo(() => strokes.flat(), [strokes]);

  // Match the sketch to walkable paths whenever it changes. A newer sketch
  // makes the older request's answer stale, so that answer is dropped.
  useEffect(() => {
    setRoute(null);
    setError('');
    if (!sketch.length) {
      setSnapping(false);
      return undefined;
    }
    let cancelled = false;
    setSnapping(true);
    snapToWalkable(sketch)
      .then((result) => {
        if (cancelled) return;
        setRoute(result);
        setSnapping(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.data?.message || "Couldn't match your route to walkable paths.");
        setSnapping(false);
      });
    return () => { cancelled = true; };
  }, [sketch, attempt]);

  const addStroke = (points) => setStrokes((all) => [...all, points]);
  const undo = () => setStrokes((all) => all.slice(0, -1));
  const clear = () => setStrokes([]);

  if (!location) {
    return (
      <div className="route-planner route-planner--loading">
        <p className="muted">Finding you…</p>
      </div>
    );
  }

  const routeEnd = route && route.coordinates[route.coordinates.length - 1];
  const routeStart = route && route.coordinates[0];

  let status;
  if (error) {
    status = (
      <>
        <p className="error">{error}</p>
        <button type="button" className="route-card__retry" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </>
    );
  } else if (snapping) {
    status = <p className="muted">Matching your route to walkable paths…</p>;
  } else if (route) {
    status = (
      <>
        <p className="route-card__distance">{formatMiles(route.distance_meters)}</p>
        {route.adjusted && (
          <p className="muted">Parts of your drawing weren't on a walkable path, so they were moved onto the nearest one.</p>
        )}
        {route.gaps.length > 0 && (
          <p className="muted">Dashed red stretches can't be reached on foot.</p>
        )}
      </>
    );
  } else if (drawing) {
    status = <p className="muted">Drag across the map to trace your route.</p>;
  } else {
    status = <p className="muted">Tap Draw route, then trace where you want to go.</p>;
  }

  return (
    <div className={`route-planner${drawing ? ' route-planner--drawing' : ''}`}>
      <MapContainer
        className="route-planner__map"
        center={[location.lat, location.lng]}
        zoom={16}
        zoomControl={false}
        attributionControl={false}
      >
        {/* The map tiles and the walking routes both come from OpenStreetMap, whose licence requires this credit */}
        <AttributionControl position="topright" prefix={false} />
        <ZoomControl position="topleft" />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        <CircleMarker
          center={[location.lat, location.lng]}
          radius={8}
          pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#1a9be6', fillOpacity: 1, interactive: false }}
        />
        {sketch.length > 1 && (
          <Polyline positions={sketch} pathOptions={route ? STYLE.sketchGhost : STYLE.sketch} />
        )}
        {route && (
          <>
            <Polyline positions={route.coordinates} pathOptions={STYLE.casing} />
            <Polyline positions={route.coordinates} pathOptions={STYLE.route} />
            {route.gaps.map((gap, i) => (
              // eslint-disable-next-line react/no-array-index-key
              <Polyline key={i} positions={gap} pathOptions={STYLE.gap} />
            ))}
            <CircleMarker
              center={routeStart}
              radius={7}
              pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#2e7d32', fillOpacity: 1, interactive: false }}
            />
            <CircleMarker
              center={routeEnd}
              radius={7}
              pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#c0392b', fillOpacity: 1, interactive: false }}
            />
          </>
        )}
        <DrawLayer active={drawing} onStroke={addStroke} />
      </MapContainer>

      {locationError && (
        <div className="route-planner__notice">{locationError}. Showing a sample area.</div>
      )}

      <section className="route-card" aria-live="polite">
        <div className="route-card__status">{status}</div>
        <div className="route-card__actions">
          <button
            type="button"
            className={`route-btn route-btn--primary${drawing ? ' route-btn--active' : ''}`}
            aria-pressed={drawing}
            onClick={() => setDrawing((d) => !d)}
          >
            {drawing ? 'Stop drawing' : (strokes.length ? 'Keep drawing' : 'Draw route')}
          </button>
          <button type="button" className="route-btn" onClick={undo} disabled={!strokes.length}>Undo</button>
          <button type="button" className="route-btn" onClick={clear} disabled={!strokes.length}>Clear</button>
        </div>
      </section>
    </div>
  );
}
