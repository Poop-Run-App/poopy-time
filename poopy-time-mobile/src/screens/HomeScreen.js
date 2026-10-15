import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { useUser } from '../context/UserContext';
import styles from '../components/FormStyles';

export default function HomeScreen() {
  const { user, logout } = useUser();

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>Hi{user?.display_name ? `, ${user.display_name}` : ''}!</Text>
      <Text style={styles.muted}>Your Poopy Time home screen. Build features here.</Text>
      <TouchableOpacity style={styles.button} onPress={logout}>
        <Text style={styles.buttonText}>Log out</Text>
      </TouchableOpacity>
    </View>
  );
}
