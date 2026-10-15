// Dynamic config layered on app.json. Add EAS-injected values here
// (e.g. process.env.GOOGLE_SERVICES_JSON once push notifications are added).
const appJson = require('./app.json');

module.exports = () => ({
  expo: {
    ...appJson.expo,
    scheme: appJson.expo.scheme ?? 'poopy-time',
    plugins: [...(appJson.expo.plugins || []), 'expo-dev-client'],
  },
});
