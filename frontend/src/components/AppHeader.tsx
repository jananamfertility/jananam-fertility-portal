import { useAuth } from "../context/AuthContext";

export type AppTab = "calendar" | "admin";

interface Props {
  tab: AppTab;
  onTabChange: (tab: AppTab) => void;
}

export default function AppHeader({ tab, onTabChange }: Props) {
  const { session, profile, isAdmin, signOut } = useAuth();

  return (
    <header className="app-header">
      <div>
        <h1>Jananam Fertility Centre</h1>
        <p className="subtitle">Front Office Portal</p>
      </div>

      <nav className="tab-nav" aria-label="Sections">
        <button
          className={`tab-btn ${tab === "calendar" ? "active" : ""}`}
          onClick={() => onTabChange("calendar")}
        >
          Calendar
        </button>
        {isAdmin && (
          <button
            className={`tab-btn ${tab === "admin" ? "active" : ""}`}
            onClick={() => onTabChange("admin")}
          >
            Admin
          </button>
        )}
      </nav>

      <div className="header-actions">
        <span className="user-email">
          {profile?.full_name ?? session?.user?.email}
          {isAdmin && <span className="admin-tag">Admin</span>}
        </span>
        <button className="btn-secondary" onClick={() => signOut()}>
          Sign out
        </button>
      </div>
    </header>
  );
}
