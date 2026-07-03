import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("pulse_token"));
  const [user, setUser] = useState(null);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const [me, projects] = await Promise.all([api.me(), api.listProjects()]);
      setUser(me);
      setProject(projects[0] || null);
    } catch {
      logout();
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const login = async (email, password) => {
    const { access_token } = await api.login(email, password);
    localStorage.setItem("pulse_token", access_token);
    setToken(access_token);
  };

  const register = async (payload) => {
    const { access_token } = await api.register(payload);
    localStorage.setItem("pulse_token", access_token);
    setToken(access_token);
  };

  const logout = () => {
    localStorage.removeItem("pulse_token");
    setToken(null);
    setUser(null);
    setProject(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, project, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
