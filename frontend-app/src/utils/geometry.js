// Helpers for freehand paths. A path is an array of [lat, lng] pairs.

const EARTH_RADIUS_METERS = 6371008.8;
const toRad = (degrees) => (degrees * Math.PI) / 180;

export function haversineMeters(a, b) {
  const dLat = toRad(b[0] - a[0]);
  const dLng = toRad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(h));
}

export function pathLengthMeters(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += haversineMeters(points[i - 1], points[i]);
  return total;
}

// Flat x/y in meters; accurate enough across a city
function project(points) {
  const kx = EARTH_RADIUS_METERS * Math.cos(toRad(points[0][0]));
  return points.map(([lat, lng]) => [toRad(lng) * kx, toRad(lat) * EARTH_RADIUS_METERS]);
}

function distanceToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  const t = lengthSq
    ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq))
    : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

// Ramer-Douglas-Peucker: drops points that sit within `toleranceMeters` of
// the line between the points kept on either side, so corners survive
export function simplify(points, toleranceMeters) {
  if (points.length < 3) return points.slice();
  const xy = project(points);
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let farthest = -1;
    let farthestDistance = toleranceMeters;
    for (let i = first + 1; i < last; i += 1) {
      const d = distanceToSegment(xy[i], xy[first], xy[last]);
      if (d > farthestDistance) {
        farthest = i;
        farthestDistance = d;
      }
    }
    if (farthest !== -1) {
      keep[farthest] = 1;
      stack.push([first, farthest], [farthest, last]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

// Adds points so no two neighbours are further apart than `maxSpacingMeters`
export function densify(points, maxSpacingMeters) {
  if (!points.length) return [];
  const out = [points[0]];
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1];
    const b = points[i];
    const steps = Math.ceil(haversineMeters(a, b) / maxSpacingMeters);
    for (let s = 1; s < steps; s += 1) {
      const t = s / steps;
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
    out.push(b);
  }
  return out;
}

// Boils a freehand stroke (hundreds of points) down to the waypoints worth
// routing through: corners are kept, straight runs are thinned, and long
// stretches get a point every `spacingMeters` so the route can't wander far
// from the line. Never returns more than `maxPoints`.
export function toWaypoints(points, { toleranceMeters = 10, spacingMeters = 100, maxPoints = 240 } = {}) {
  let tolerance = toleranceMeters;
  for (;;) {
    const simple = simplify(points, tolerance);
    if (simple.length <= maxPoints / 2 || simple.length <= 2) {
      const spacing = Math.max(spacingMeters, pathLengthMeters(simple) / (maxPoints / 2));
      return densify(simple, spacing);
    }
    tolerance *= 1.6;
  }
}
