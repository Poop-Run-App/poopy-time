import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import './appShell.css';

function RouteIcon() {
  return (
    <svg viewBox="0 0 40 20" width="40" height="20" aria-hidden="true">
      <circle cx="4" cy="14" r="3" fill="currentColor" />
      <path d="M8 14 Q16 4 26 12" fill="none" stroke="var(--color-error)" strokeWidth="2" strokeDasharray="3 3" />
      <path d="M30 6 L36 12 M36 6 L30 12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function EmergencyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
      <path d="M12 3 L22 20 H2 Z" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}

function ProfileIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
      <circle cx="12" cy="8" r="5" fill="currentColor" />
      <path d="M3 22 C3 15 21 15 21 22 Z" fill="currentColor" />
    </svg>
  );
}

const tabClass = ({ isActive }) => `tab${isActive ? ' tab--active' : ''}`;

export default function AppShell() {
  return (
    <div className="app-shell">
      <main className="app-shell__content">
        <Outlet />
      </main>
      <nav className="tab-bar" aria-label="Main">
        <NavLink to="/home/route" className={tabClass} aria-label="Route"><RouteIcon /></NavLink>
        <NavLink to="/home" end className={tabClass} aria-label="Emergency"><EmergencyIcon /></NavLink>
        <NavLink to="/home/profile" className={tabClass} aria-label="Profile"><ProfileIcon /></NavLink>
      </nav>
    </div>
  );
}
