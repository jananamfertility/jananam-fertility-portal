import { useState } from "react";
import ProvidersAdmin from "../components/admin/ProvidersAdmin";
import StaffAdmin from "../components/admin/StaffAdmin";
import ReportsAdmin from "../components/admin/ReportsAdmin";
import MarketingAdmin from "../components/admin/MarketingAdmin";

type AdminTab = "providers" | "staff" | "reports" | "marketing";

export default function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("reports");

  return (
    <div className="page-section">
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
          Marketing
        </button>
      </div>

      {tab === "reports" && <ReportsAdmin />}
      {tab === "providers" && <ProvidersAdmin />}
      {tab === "staff" && <StaffAdmin />}
      {tab === "marketing" && <MarketingAdmin />}
    </div>
  );
}
