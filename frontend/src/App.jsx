import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Queues from "./pages/Queues";
import JobExplorer from "./pages/JobExplorer";
import Workers from "./pages/Workers";
import DeadLetter from "./pages/DeadLetter";

function Protected({ children }) {
  const { token, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center text-muted text-sm bg-void">Loading...</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Overview /></Protected>} />
      <Route path="/queues" element={<Protected><Queues /></Protected>} />
      <Route path="/jobs" element={<Protected><JobExplorer /></Protected>} />
      <Route path="/workers" element={<Protected><Workers /></Protected>} />
      <Route path="/dead-letter" element={<Protected><DeadLetter /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
