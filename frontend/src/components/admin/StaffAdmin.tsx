import { useEffect, useState } from "react";
import { createStaff, fetchStaff, updateStaff } from "../../lib/api";
import type { StaffAccount, StaffRole } from "../../lib/types";
import { useAuth } from "../../context/AuthContext";

export default function StaffAdmin() {
  const { profile } = useAuth();
  const [staff, setStaff] = useState<StaffAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<StaffRole>("front_office");

  async function load() {
    setLoading(true);
    try {
      const data = await fetchStaff();
      setStaff(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd() {
    setError(null);
    if (!email.trim() || !fullName.trim() || password.length < 8) {
      setError("Email, name, and an 8+ character temporary password are required.");
      return;
    }
    setSaving(true);
    try {
      await createStaff({ email: email.trim(), full_name: fullName.trim(), password, role });
      setEmail("");
      setFullName("");
      setPassword("");
      setRole("front_office");
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Could not create this account.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(s: StaffAccount) {
    try {
      await updateStaff(s.id, { is_active: !s.is_active });
      load();
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Could not update this account.");
    }
  }

  async function changeRole(s: StaffAccount, newRole: StaffRole) {
    try {
      await updateStaff(s.id, { role: newRole });
      load();
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Could not update this account.");
    }
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-header">
        <h2>Staff accounts</h2>
        <p className="panel-sub">Front-office logins for this portal. Each person should have their own account.</p>
      </div>

      <div className="admin-card">
        <h3>Add a staff account</h3>
        <div className="field-row">
          <div className="field">
            <label htmlFor="s_email">Email</label>
            <input id="s_email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="s_name">Full name</label>
            <input id="s_name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="s_password">Temporary password</label>
            <input
              id="s_password"
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          <div className="field">
            <label htmlFor="s_role">Role</label>
            <select id="s_role" value={role} onChange={(e) => setRole(e.target.value as StaffRole)}>
              <option value="front_office">Front office</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="field field-btn">
            <button className="btn-primary" onClick={handleAdd} disabled={saving}>
              {saving ? "Creating…" : "Create account"}
            </button>
          </div>
        </div>
        {error && <p className="error-text">{error}</p>}
        <p className="hint">Share the temporary password with them directly — they can change it after signing in.</p>
      </div>

      <div className="admin-table-wrap">
        {loading ? (
          <p className="panel-sub">Loading…</p>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {staff.map((s) => {
                const isSelf = s.id === profile?.id;
                return (
                  <tr key={s.id} className={!s.is_active ? "row-muted" : ""}>
                    <td>
                      {s.full_name}
                      {isSelf && <span className="you-tag">You</span>}
                    </td>
                    <td>{s.email ?? "—"}</td>
                    <td>
                      <select
                        value={s.role}
                        disabled={isSelf}
                        onChange={(e) => changeRole(s, e.target.value as StaffRole)}
                      >
                        <option value="front_office">Front office</option>
                        <option value="admin">Admin</option>
                      </select>
                    </td>
                    <td>
                      <span className={`pill ${s.is_active ? "pill-active" : "pill-inactive"}`}>
                        {s.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn-secondary btn-sm"
                        disabled={isSelf}
                        onClick={() => toggleActive(s)}
                      >
                        {s.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
