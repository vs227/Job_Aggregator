import { createContext, useContext, useState, useEffect } from 'react';
import { fetchProfile, logoutUser } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    fetchProfile()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
        window.location.href = '/login';
      })
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;

    function checkTokenExpiry() {
      try {
        const parts = token.split('.');
        if (parts.length === 3) {
          const payload = JSON.parse(atob(parts[1]));
          if (payload.exp && Date.now() >= payload.exp * 1000) {
            console.warn("Session finished / token expired. Auto logging out...");
            localStorage.removeItem('token');
            setToken(null);
            setUser(null);
            window.location.href = '/login';
          }
        }
      } catch (e) {
        // Ignore parsing error
      }
    }

    checkTokenExpiry();
    const interval = setInterval(checkTokenExpiry, 10000);
    return () => clearInterval(interval);
  }, [token]);

  function login(newToken) {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  }

  async function logout() {
    try {
      await logoutUser();
    } catch (err) {
      console.warn("Logout endpoint notice:", err);
    } finally {
      localStorage.removeItem('token');
      setToken(null);
      setUser(null);
      window.location.href = '/login';
    }
  }


  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
