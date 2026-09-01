import { useEffect, useState } from "react";
import { createProvider, fetchProviders, updateProvider } from "../../lib/api";
import type { Provider } from "../../lib/types";

export default function ProvidersAdmin() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [designation, setDesignation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await fetchProviders(true);
      setProviders(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd() {
    if (!name.trim()) {
      setError("Provider name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createProvider({ name: name.trim(), designation: designation.trim() || null });
      setName("");
      setDesignation("");
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Could not add provider.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(p: Provider) {
    await updateProvider(p.id, { name: p.name, designation: p.designation, is_active: !p.is_active });
    load();
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-header">
        <h2>Doctors &amp; providers</h2>
        <p className="panel-sub">Who appointments can be booked with. Deactivate instead of deleting to keep past appointment history intact.</p>
      </div>

      <div className="admin-card">
        <h3>Add a provider</h3>
        <div className="field-row">
          <div className="field">
            <label htmlFor="p_name">Name</label>
            <input id="p_name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Full Name" />
          </div>
          <div className="field">
            <label htmlFor="p_designation">Designation</label>
            <input
              id="p_designation"
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              placeholder="Fertility Consultant"
            />
          </div>
          <div className="field field-btn">
            <button className="btn-primary" onClick={handleAdd} disabled={saving}>
              {saving ? "Adding…" : "Add"}
            </button>
          </div>
        </div>
        {error && <p className="error-text">{error}</p>}
      </div>

      <div className="admin-table-wrap">
        {loading ? (
          <p className="panel-sub">Loading…</p>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Designation</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr key={p.id} className={!p.is_active ? "row-muted" : ""}>
                  <td>{p.name}</td>
                  <td>{p.designation || "—"}</td>
                  <td>
                    <span className={`pill ${p.is_active ? "pill-active" : "pill-inactive"}`}>
                      {p.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td>
                    <button className="btn-secondary btn-sm" onClick={() => toggleActive(p)}>
                      {p.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
              {providers.length === 0 && (
                <tr>
                  <td colSpan={4} className="panel-sub">
                    No providers yet — add one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
