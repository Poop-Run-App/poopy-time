import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, CircleMarker, AttributionControl, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { fetchNearbyBathrooms, hoursStatus } from '../../data/bathrooms';
import './emergency.css';

// Used when the browser can't or won't share a location
const FALLBACK_LOCATION = { lat: 40.7128, lng: -74.006 };

const pinIcon = (number, selected) => L.divIcon({
  className: '',
  html: `<div class="pin${selected ? ' pin--selected' : ''}"><span>${number}</span></div>`,
  iconSize: [32, 42],
  iconAnchor: [16, 42],
});

// Keeps the bottom card from covering pins
const MAP_PADDING = { paddingTopLeft: [40, 60], paddingBottomRight: [40, 180] };

// Frames the user and every bathroom once, then only pans when the
// selected pin would be off screen
function KeepInView({ location, bathrooms, selected }) {
  const map = useMap();
  const framed = useRef(false);
  useEffect(() => {
    if (framed.current || !bathrooms.length) return;
    framed.current = true;
    const points = [[location.lat, location.lng], ...bathrooms.map((b) => [b.latitude, b.longitude])];
    map.fitBounds(points, MAP_PADDING);
  }, [map, location, bathrooms]);
  useEffect(() => {
    if (selected) map.panInside([selected.latitude, selected.longitude], MAP_PADDING);
  }, [map, selected]);
  return null;
}

export default function Emergency() {
  const [location, setLocation] = useState(null);
  const [locationError, setLocationError] = useState('');
  const [selected, setSelected] = useState(0);
  const [showInfo, setShowInfo] = useState(false);

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

  // The API returns nearest first, so pin numbers match the order "next" walks through
  const [bathrooms, setBathrooms] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!location) return;
    let cancelled = false;
    fetchNearbyBathrooms(location)
      .then((list) => { if (!cancelled) setBathrooms(list); })
      .catch(() => {
        if (cancelled) return;
        setLoadError("Couldn't load nearby bathrooms");
        setBathrooms([]);
      });
    return () => { cancelled = true; };
  }, [location]);

  if (!location || !bathrooms) {
    return (
      <div className="emergency emergency--loading">
        <p className="muted">{location ? 'Finding bathrooms…' : 'Finding you…'}</p>
      </div>
    );
  }

  const notice = [
    locationError && `${locationError}. Showing a sample area.`,
    loadError,
    !loadError && !bathrooms.length && 'No bathrooms found within a mile.',
  ].filter(Boolean).join(' ');

  const current = bathrooms[selected];
  const hours = current && hoursStatus(current);

  const select = (i) => { setSelected(i); setShowInfo(false); };
  const next = () => select((selected + 1) % bathrooms.length);
  const directionsUrl = current
    && `https://www.google.com/maps/dir/?api=1&destination=${current.latitude},${current.longitude}&travelmode=walking`;

  return (
    <div className="emergency">
      <MapContainer
        className="emergency__map"
        center={[location.lat, location.lng]}
        zoom={16}
        zoomControl={false}
        attributionControl={false}
      >
        {/* The map tiles and imported toilets both come from OpenStreetMap, whose licence requires this credit */}
        <AttributionControl position="topright" prefix={false} />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        <CircleMarker
          center={[location.lat, location.lng]}
          radius={8}
          pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#1a9be6', fillOpacity: 1 }}
        />
        {bathrooms.map((b, i) => (
          <Marker
            key={b.id}
            position={[b.latitude, b.longitude]}
            icon={pinIcon(i + 1, i === selected)}
            eventHandlers={{ click: () => select(i) }}
          />
        ))}
        <KeepInView location={location} bathrooms={bathrooms} selected={current} />
      </MapContainer>

      {notice && <div className="emergency__notice">{notice}</div>}

      {current && (
        <div className="bathroom-card-row">
          <section className="bathroom-card" aria-live="polite">
            <h2 className="bathroom-card__name">{current.name}</h2>
            <div className="bathroom-card__bottom">
              <div className="bathroom-card__meta">
                <p className={`bathroom-card__hours bathroom-card__hours--${hours.tone}`}>
                  {hours.text}
                </p>
                <p>{current.distance_miles.toFixed(1)} miles away</p>
              </div>
              <div className="bathroom-card__actions">
                <button
                  className="icon-btn icon-btn--info"
                  aria-label="Bathroom details"
                  aria-expanded={showInfo}
                  onClick={() => setShowInfo((v) => !v)}
                >
                  i
                </button>
                <a
                  className="icon-btn icon-btn--go"
                  href={directionsUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Directions to ${current.name}`}
                >
                  <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                    <path d="M7 4 L20 12 L7 20 Z" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
                  </svg>
                </a>
              </div>
            </div>
            {showInfo && (
              <div className="bathroom-card__info muted">
                {current.address && <p>{current.address}</p>}
                <p>{current.is_accessible ? 'Wheelchair accessible' : 'Accessibility unknown'}</p>
                {current.notes && <p>{current.notes}</p>}
              </div>
            )}
          </section>
          {bathrooms.length > 1 && (
            <button className="bathroom-card-row__next" aria-label="Next bathroom" onClick={next}>
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <path d="M9 4 L17 12 L9 20" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
