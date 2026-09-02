import { useEffect, useState } from "react";
import ProvidersAdmin from "../components/admin/ProvidersAdmin";
import StaffAdmin from "../components/admin/StaffAdmin";
import ReportsAdmin from "../components/admin/ReportsAdmin";
import MarketingAdmin from "../components/admin/MarketingAdmin";
import { fetchAlerts } from "../lib/api";

type AdminTab = "providers" | "staff" | "reports" | "marketing";

const ALERT_POLL_MS = 60_000;

export default function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("reports");
  const [alertCount, setAlertCount] = useState(0);

  // Polled from every admin tab (not just Marketing) so an urgent WhatsApp
  // alert doesn't sit unnoticed just because staff are on a different tab.
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const alerts = await fetchAlerts({ unacknowledged_only: true });
        if (!cancelled) setAlertCount(alerts.length);
      } catch {
        // non-fatal — the Marketing tab will still show alerts once opened
      }
    }
    poll();
    const id = setInterval(poll, ALERT_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="page-section">
      {alertCount > 0 && (
        <div
          className="admin-card"
          style={{ borderLeft: "4px solid #c0392b", background: "#fdf1f0", cursor: "pointer" }}
          onClick={() => setTab("marketing")}
        >
          ⚠️ {alertCount} WhatsApp alert{alertCount === 1 ? "" : "s"} need attention — click to review in
          Marketing.
        </div>
      )}

      <div className="admin-tabs">
        <button className={`tab-btn ${tab === "reports" ? "active" : ""}`} onClick={() => setTab("reports")}>
          Reports
        </button>
        <button className={`tab-btn ${tab === "providers" ? "active" : ""}`} onClick={() => setTab("providers")}>
          Doctors &amp; providers
        </button>
        <button className={`tab-btn ${tab === "staff" ? "active" : ""}`} onClick={() => setTab("staff")}>
          Staff accounts
        </button>
        <button className={`tab-btn ${tab === "marketing" ? "active" : ""}`} onClick={() => setTab("marketing")}>
          Marketing{alertCount > 0 ? ` (${alertCount})` : ""}
        </button>
      </div>

      {tab === "reports" && <ReportsAdmin />}
      {tab === "providers" && <ProvidersAdmin />}
      {tab === "staff" && <StaffAdmin />}
      {tab === "marketing" && <MarketingAdmin />}
    </div>
  );
}
