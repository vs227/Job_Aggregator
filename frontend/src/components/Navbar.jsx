import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { HiOutlineMenu, HiOutlineX } from 'react-icons/hi';
import { MdDashboard, MdBookmark, MdNotifications, MdLightMode, MdDarkMode, MdContactPage, MdLogout } from 'react-icons/md';
import { useAuth } from '../context/AuthContext';
import logo from '../assets/logo.png';
import './Navbar.css';

function Navbar() {
  const { isAuthenticated, user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark');
  const navigate = useNavigate();
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setProfileOpen(false);
        setMenuOpen(false);
      }
    }
    if (profileOpen || menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [profileOpen, menuOpen]);

  function toggleTheme() {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem('theme', nextTheme);
  }

  function handleLogout() {
    logout();
    navigate('/');
  }

  return (
    <>
      <nav className="navbar">
        <div className="navbar-container navbar-inner">
          <Link to="/" className="navbar-logo">
            <img src={logo} alt="HirePulse" className="navbar-logo-img" />
          </Link>

          {/* DESKTOP NAV LINKS (PC UI Only) */}
          {isAuthenticated && (
            <div className="desktop-navbar-links">
              <NavLink to="/dashboard" title="Dashboard">
                <MdDashboard /> <span className="nav-text">Dashboard</span>
              </NavLink>
              <NavLink to="/saved" title="Saved">
                <MdBookmark /> <span className="nav-text">Saved</span>
              </NavLink>
              <NavLink to="/alerts" title="Alerts">
                <MdNotifications /> <span className="nav-text">Alerts</span>
              </NavLink>
              <NavLink to="/resume" title="Resume">
                <MdContactPage /> <span className="nav-text">Resume</span>
              </NavLink>
            </div>
          )}

          {/* RIGHT SIDE CONTROLS */}
          <div className="navbar-controls-wrapper" ref={dropdownRef}>
            {/* Desktop User Profile Avatar (PC UI Only) */}
            {isAuthenticated && (
              <div className="desktop-user-profile">
                <div 
                  className="navbar-user" 
                  onClick={() => setProfileOpen(!profileOpen)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="navbar-avatar">
                    {user?.username?.charAt(0).toUpperCase() || 'U'}
                  </div>
                  <span className="navbar-username">{user?.username || 'User'}</span>
                </div>

                {profileOpen && (
                  <div className="navbar-profile-dropdown glass">
                    <div className="dropdown-user-info">
                      <div className="dropdown-username">{user?.username || 'User'}</div>
                      <div className="dropdown-email">{user?.email || ''}</div>
                    </div>
                    <div className="dropdown-divider"></div>
                    <button 
                      className="dropdown-item logout-item"
                      onClick={() => {
                        setProfileOpen(false);
                        handleLogout();
                      }}
                    >
                      <MdLogout /> Logout
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Light/Dark Theme Toggle (PC & Mobile) */}
            <button className="theme-toggle-btn" onClick={toggleTheme} title="Toggle Theme">
              {theme === 'dark' ? <MdLightMode /> : <MdDarkMode />}
            </button>

            {/* Menu Toggle Button (Mobile Phone ONLY) */}
            <button 
              className="navbar-menu-toggle-btn" 
              onClick={() => setMenuOpen(!menuOpen)} 
              title="Menu"
              aria-label="Toggle Mobile Menu"
            >
              {menuOpen ? <HiOutlineX /> : <HiOutlineMenu />}
            </button>

            {/* Mobile Side Drawer (Mobile Phone ONLY) */}
            {menuOpen && (
              <div className="navbar-side-drawer">
                {isAuthenticated ? (
                  <>
                    <div className="drawer-user-header">
                      <div className="drawer-user-avatar">
                        {user?.username?.charAt(0).toUpperCase() || 'U'}
                      </div>
                      <div className="drawer-user-details">
                        <span className="drawer-username">{user?.username || 'User'}</span>
                        <span className="drawer-email">{user?.email || ''}</span>
                      </div>
                    </div>

                    <div className="drawer-divider"></div>

                    <button 
                      className="drawer-nav-item logout-btn" 
                      onClick={() => {
                        setMenuOpen(false);
                        handleLogout();
                      }}
                    >
                      <MdLogout /> Logout
                    </button>
                  </>
                ) : (
                  <>
                    <NavLink to="/login" className="drawer-nav-item" onClick={() => setMenuOpen(false)}>
                      Sign In
                    </NavLink>
                    <NavLink to="/register" className="drawer-nav-item primary" onClick={() => setMenuOpen(false)}>
                      Sign Up
                    </NavLink>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* SPECIAL SUB NAVBAR BELOW NAVBAR (Mobile Phone ONLY) */}
      {isAuthenticated && (
        <div className="mobile-only-sub-navbar">
          <div className="sub-navbar-container">
            <div className="sub-navbar-pills">
              <NavLink to="/dashboard" className={({ isActive }) => `sub-pill-link ${isActive ? 'active' : ''}`}>
                <MdDashboard /> <span>Dashboard</span>
              </NavLink>
              <NavLink to="/saved" className={({ isActive }) => `sub-pill-link ${isActive ? 'active' : ''}`}>
                <MdBookmark /> <span>Saved</span>
              </NavLink>
              <NavLink to="/alerts" className={({ isActive }) => `sub-pill-link ${isActive ? 'active' : ''}`}>
                <MdNotifications /> <span>Alerts</span>
              </NavLink>
              <NavLink to="/resume" className={({ isActive }) => `sub-pill-link ${isActive ? 'active' : ''}`}>
                <MdContactPage /> <span>Resume AI</span>
              </NavLink>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default Navbar;
