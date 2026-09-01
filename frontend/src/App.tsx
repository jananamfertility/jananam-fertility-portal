import { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";
import CalendarPage from "./pages/CalendarPage";
import AdminPage from "./pages/AdminPage";
import AppHeader, { type AppTab } from "./components/AppHeader";
import "./index.css";

function Gate() {
  const { session, loading, isAdmin } = useAuth();
  const [tab, setTab] = useState<AppTab>("calendar");

  if (loading) return <div className="loading-screen">Loading…</div>;
  if (!session) return <LoginPage />;

  const activeTab = tab === "admin" && !isAdmin ? "calendar" : tab;

  return (
    <div className="app-shell">
      <AppHeader tab={activeTab} onTabChange={setTab} />
      {activeTab === "calendar" ? <CalendarPage /> : <AdminPage />}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
