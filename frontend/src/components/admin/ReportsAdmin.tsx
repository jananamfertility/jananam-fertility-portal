import { useEffect, useMemo, useState } from "react";
import { fetchReportSummary } from "../../lib/api";
import type { ReportSummary } from "../../lib/types";
import { APPOINTMENT_STATUS_LABELS, APPOINTMENT_TYPE_LABELS } from "../../lib/types";

// Validated (dataviz skill) 3-slot categorical palette — passes chroma floor,
// CVD adjacent-pair separation and normal-vision floor in both light & dark.
const TYPE_COLORS: Record<string, string> = {
  consultation: "#1f8f61",
  follow_up: "#2a78d6",
  nt_scan: "#c94f86",
};
const WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function monthInputValue(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function monthRange(value: string): { start: string; end: string } {
  const [y, m] = value.split("-").map(Number);
  const start = new Date(y, m - 1, 1);
  const end = new Date(y, m, 1);
  return { start: start.toISOString(), end: end.toISOString() };
}

function Bar({ label, value, max, color, sublabel }: { label: string; value: number; max: number; color: string; sublabel?: string }) {
  const pct = max > 0 ? Math.max((value / max) * 100, value > 0 ? 3 : 0) : 0;
  return (
    <div className="bar-row">
      <div className="bar-label">
        {color && <span className="bar-dot" style={{ background: color }} />}
        <span>{label}</span>
        {sublabel && <span className="bar-sublabel">{sublabel}</span>}
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="bar-value num">{value}</div>
    </div>
  );
}

export default function ReportsAdmin() {
  const [month, setMonth] = useState(monthInputValue(new Date()));
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const { start, end } = monthRange(month);
    fetchReportSummary({ start, end })
      .then(setSummary)
      .catch(() => setError("Could not load the report for this month."))
      .finally(() => setLoading(false));
  }, [month]);

  const maxType = useMemo(() => (summary ? Math.max(1, ...Object.values(summary.by_type)) : 1), [summary]);
  const maxWeekday = useMemo(
    () => (summary ? Math.max(1, ...WEEKDAY_ORDER.map((d) => summary.by_weekday[d] ?? 0)) : 1),
    [summary]
  );
  const maxProvider = useMemo(
    () => (summary ? Math.max(1, ...Object.values(summary.by_provider)) : 1),
    [summary]
  );

  return (
    <div className="admin-panel">
      <div className="admin-panel-header admin-panel-header-row">
        <div>
          <h2>Booking reports</h2>
          <p className="panel-sub">Volume and outcomes for the selected month.</p>
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          aria-label="Select month"
        />
      </div>

      {loading && <p className="panel-sub">Loading…</p>}
      {error && <p className="error-text">{error}</p>}

      {summary && !loading && (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="stat-value num">{summary.total}</div>
              <div className="stat-label">Total booked</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{summary.kept}</div>
              <div className="stat-label">Kept (not cancelled)</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{(summary.no_show_rate * 100).toFixed(1)}%</div>
              <div className="stat-label">No-show rate</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{(summary.cancellation_rate * 100).toFixed(1)}%</div>
              <div className="stat-label">Cancellation rate</div>
            </div>
          </div>

          <div className="report-grid">
            <div className="admin-card">
              <h3>By appointment type</h3>
              <div className="bar-list">
                {Object.entries(APPOINTMENT_TYPE_LABELS).map(([key, label]) => (
                  <Bar
                    key={key}
                    label={label}
                    value={summary.by_type[key] ?? 0}
                    max={maxType}
                    color={TYPE_COLORS[key]}
                  />
                ))}
              </div>
            </div>

            <div className="admin-card">
              <h3>By status</h3>
              <div className="bar-list">
                {Object.entries(APPOINTMENT_STATUS_LABELS).map(([key, label]) => (
                  <div className="bar-row" key={key}>
                    <div className="bar-label">
                      <span className={`pill status-${key}`}>{label}</span>
                    </div>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: summary.total ? `${((summary.by_status[key] ?? 0) / summary.total) * 100}%` : "0%",
                          background: "var(--muted)",
                        }}
                      />
                    </div>
                    <div className="bar-value num">{summary.by_status[key] ?? 0}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="admin-card">
              <h3>By day of week</h3>
              <p className="panel-sub">Cancelled appointments excluded — target is 3-4 on weekdays, up to 8 on Saturday.</p>
              <div className="bar-list">
                {WEEKDAY_ORDER.map((d) => (
                  <Bar
                    key={d}
                    label={d}
                    value={summary.by_weekday[d] ?? 0}
                    max={maxWeekday}
                    color="var(--accent)"
                  />
                ))}
              </div>
            </div>

            <div className="admin-card">
              <h3>By provider</h3>
              <div className="bar-list">
                {Object.entries(summary.by_provider).length === 0 && (
                  <p className="panel-sub">No appointments this month.</p>
                )}
                {Object.entries(summary.by_provider)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, count]) => (
                    <Bar key={name} label={name} value={count} max={maxProvider} color="var(--accent)" />
                  ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
