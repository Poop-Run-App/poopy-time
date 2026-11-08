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

// Bathrooms a source reports as closed go last, so the nearest open one
// comes first; the order is otherwise nearest first.
export function openFirst(bathrooms) {
  return [...bathrooms].sort((a, b) => (a.status === 'closed') - (b.status === 'closed'));
}

// The card's hours line. A reported closure wins. hours_note is the
// source's own wording: shown in place of the hour range when there is
// one, and on its own (with no open/closed status) when the hours
// couldn't be turned into a range (e.g. imported "Mo-Fr 08:00-17:00").
export function hoursStatus(bathroom, now = new Date()) {
  if (bathroom.status === 'closed') {
    return { text: bathroom.status_reason || 'Closed', tone: 'closed' };
  }
  const limited = bathroom.status === 'limited' ? ` (${bathroom.status_reason || 'limited use'})` : '';
  if (bathroom.open_hour == null && bathroom.hours_note) {
    return { text: bathroom.hours_note + limited, tone: 'unknown' };
  }
  const open = isOpen(bathroom, now);
  const hours = bathroom.hours_note || hoursLabel(bathroom);
  return { text: `${open ? 'Open' : 'Closed'} - ${hours}${limited}`, tone: open ? 'open' : 'closed' };
}

export function isOpen(bathroom, now = new Date()) {
  if (isAllDay(bathroom)) return true;
  const { open_hour: open, close_hour: close } = bathroom;
  const h = now.getHours() + now.getMinutes() / 60;
  // Hours that run past midnight, e.g. 18-2
  return open <= close ? h >= open && h < close : h >= open || h < close;
}
