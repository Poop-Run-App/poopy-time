import api from '../utils/api';
import { toWaypoints } from '../utils/geometry';

// Moves a hand-drawn path ([[lat, lng], ...]) onto walkable paths. Resolves to
// { coordinates, distance_meters, adjusted, gaps }:
//  - coordinates: the walkable route, as [lat, lng] pairs
//  - adjusted: some of the drawing was off walkable ground and got moved
//  - gaps: stretches with no walkable link, left as straight lines
export async function snapToWalkable(sketch) {
  const res = await api.post('/routes/snap', { points: toWaypoints(sketch) });
  return res.data.route;
}

export const metersToMiles = (meters) => meters / 1609.344;
