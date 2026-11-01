import api from '../utils/api';

// Nearest bathrooms first, each with distance_miles
export async function fetchNearbyBathrooms({ lat, lng }, radiusMiles = 1) {
  const res = await api.get('/bathrooms/nearby', {
    params: { lat, lng, radius_miles: radiusMiles },
  });
  return res.data.bathrooms;
}

const formatHour = (h) => {
  if (h === 0 || h === 24) return '12am';
  if (h === 12) return '12pm';
  return h < 12 ? `${h}am` : `${h - 12}pm`;
};

const isAllDay = ({ open_hour: open, close_hour: close }) =>
  open == null || (open === 0 && close === 24);

export function hoursLabel(bathroom) {
  if (isAllDay(bathroom)) return '24 hours';
  return `${formatHour(bathroom.open_hour)}-${formatHour(bathroom.close_hour)}`;
}

export function isOpen(bathroom, now = new Date()) {
  if (isAllDay(bathroom)) return true;
  const { open_hour: open, close_hour: close } = bathroom;
  const h = now.getHours() + now.getMinutes() / 60;
  // Hours that run past midnight, e.g. 18-2
  return open <= close ? h >= open && h < close : h >= open || h < close;
}
