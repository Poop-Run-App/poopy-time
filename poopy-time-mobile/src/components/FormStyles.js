import { StyleSheet } from 'react-native';
import { colors } from '../theme';

export default StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, justifyContent: 'center', padding: 24 },
  title: { fontSize: 32, fontWeight: '700', color: colors.primary, marginBottom: 24, textAlign: 'center' },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 14,
    fontSize: 16,
    marginBottom: 12,
    color: colors.text,
  },
  button: { backgroundColor: colors.primary, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4 },
  buttonText: { color: colors.primaryContrast, fontSize: 16, fontWeight: '600' },
  link: { color: colors.primary, textAlign: 'center', marginTop: 16 },
  error: { color: colors.error, marginBottom: 8 },
  muted: { color: colors.muted, textAlign: 'center', marginBottom: 24 },
});
