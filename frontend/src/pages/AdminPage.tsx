import { useState } from "react";
import ProvidersAdmin from "../components/admin/ProvidersAdmin";
import StaffAdmin from "../components/admin/StaffAdmin";
import ReportsAdmin from "../components/admin/ReportsAdmin";

type AdminTab = "providers" | "staff" | "reports";

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
      </div>

      {tab === "reports" && <ReportsAdmin />}
      {tab === "providers" && <ProvidersAdmin />}
      {tab === "staff" && <StaffAdmin />}
    </div>
  );
}
