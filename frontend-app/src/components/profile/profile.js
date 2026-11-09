import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext';

export default function Profile() {
  const navigate = useNavigate();
  const { user, logout } = useUser();

  return (
    <div className="page">
      <div className="card">
        <h1>Hi{user?.display_name ? `, ${user.display_name}` : ''}!</h1>
        <p className="muted">{user?.email}</p>
        <button onClick={() => { logout(); navigate('/'); }}>Log out</button>
      </div>
    </div>
  );
}
