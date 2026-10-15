import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { UserProvider, useUser } from './context/UserContext';
import './theme/tokens.css';
import './App.css';
import Login from './components/auth/login';
import SignUp from './components/auth/signUp';
import Home from './components/home/home';

function RequireAuth({ children }) {
  const { user } = useUser();
  return user ? children : <Navigate to="/" replace />;
}

function App() {
  return (
    <UserProvider>
      <Router>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/signup" element={<SignUp />} />
          <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </UserProvider>
  );
}

export default App;
