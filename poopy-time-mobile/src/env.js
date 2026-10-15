// For local development set EXPO_PUBLIC_API_BASE_URL in .env (e.g. http://192.168.x.x:5000).
// EAS builds set it per profile in eas.json.
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:5000';

if (__DEV__) {
  console.log('API_BASE_URL:', API_BASE_URL);
}
