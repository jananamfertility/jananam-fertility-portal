import { useEffect, useMemo, useState } from "react";
import {
  acknowledgeAlert,
  createTemplate,
  fetchAlerts,
  fetchConversations,
  fetchFunnelSummary,
  fetchIntegrationsHealth,
  fetchTemplates,
  sendRetargetCampaign,
  syncTemplateStatus,
  updateTemplate,
} from "../../lib/api";
import type {
  FunnelStage,
  FunnelSummary,
  IntegrationsHealth,
  MessageTemplate,
  StaffAlert,
  TemplateCategory,
  WhatsAppConversation,
} from "../../lib/types";
import { FUNNEL_STAGE_LABELS } from "../../lib/types";

// Sequential ramp (light → dark) — the AIDA stages are an ordered
// progression, not unrelated categories, so a same-hue ramp reads more
// correctly than distinct categorical colors would.
const STAGE_COLORS: Record<FunnelStage, string> = {
  awareness: "#bfe0cd",
  interest: "#8ccaa8",
  desire: "#57ac80",
  action: "#2f8f61",
  booked: "#1f6f47",
};
const STAGES: FunnelStage[] = ["awareness", "interest", "desire", "action", "booked"];

function monthInputValue(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function monthRange(value: string): { start: string; end: string } {
  const [y, m] = value.split("-").map(Number);
  return { start: new Date(y, m - 1, 1).toISOString(), end: new Date(y, m, 1).toISOString() };
}
function timeAgo(iso?: string | null): string {
  if (!iso) return "Never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days ago`;
}

function FunnelBar({ stage, value, max }: { stage: FunnelStage; value: number; max: number }) {
  const pct = max > 0 ? Math.max((value / max) * 100, value > 0 ? 3 : 0) : 0;
  return (
    <div className="bar-row">
      <div className="bar-label">
        <span className="bar-dot" style={{ background: STAGE_COLORS[stage] }} />
        <span>{FUNNEL_STAGE_LABELS[stage]}</span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: STAGE_COLORS[stage] }} />
      </div>
      <div className="bar-value num">{value}</div>
    </div>
  );
}

export default function MarketingAdmin() {
  const [month, setMonth] = useState(monthInputValue(new Date()));
  const [summary, setSummary] = useState<FunnelSummary | null>(null);
  const [conversations, setConversations] = useState<WhatsAppConversation[]>([]);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [alerts, setAlerts] = useState<StaffAlert[]>([]);
  const [health, setHealth] = useState<IntegrationsHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tName, setTName] = useState("");
  const [tCategory, setTCategory] = useState<TemplateCategory>("marketing");
  const [tBody, setTBody] = useState("");
  const [tStage, setTStage] = useState<FunnelStage>("desire");
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [campaignBusy, setCampaignBusy] = useState<string | null>(null);
  const [campaignResult, setCampaignResult] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const { start, end } = monthRange(month);
      const [s, c, t, a, h] = await Promise.all([
        fetchFunnelSummary({ start, end }),
        fetchConversations(),
        fetchTemplates(),
        fetchAlerts({ unacknowledged_only: true }),
        fetchIntegrationsHealth().catch(() => null),
      ]);
      setSummary(s);
      setConversations(c);
      setTemplates(t);
      setAlerts(a);
      setHealth(h);
    } catch {
      setError("Could not load marketing data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  async function handleAcknowledge(alertId: string) {
    await acknowledgeAlert(alertId);
    setAlerts((prev) => prev.filter((a) => a.id !== alertId));
  }

  async function handleSyncStatus(t: MessageTemplate) {
    setSyncingId(t.id);
    try {
      await syncTemplateStatus(t.id);
      await load();
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Could not verify this template's status with Meta yet.");
    } finally {
      setSyncingId(null);
    }
  }

  const maxFunnel = useMemo(
    () => (summary ? Math.max(1, ...STAGES.map((s) => summary.ever_reached_by_stage[s] ?? 0)) : 1),
    [summary]
  );

  async function handleCreateTemplate() {
    setError(null);
    if (!tName.trim() || !tBody.trim()) {
      setError("Template name and body are required.");
      return;
    }
    setSavingTemplate(true);
    try {
      await createTemplate({
        name: tName.trim(),
        category: tCategory,
        body: tBody.trim(),
        variables: [],
        target_stage: tStage,
      });
      setTName("");
      setTBody("");
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Could not create this template.");
    } finally {
      setSavingTemplate(false);
    }
  }

  async function markSubmitted(t: MessageTemplate) {
    await updateTemplate(t.id, { status: "submitted" });
    load();
  }
  async function markApproved(t: MessageTemplate) {
    const metaName = prompt(
      "Exact template name as approved in Meta Business Manager (usually same as this name):",
      t.name
    );
    if (metaName === null) return;
    await updateTemplate(t.id, { status: "approved", meta_template_name: metaName || t.name });
    load();
  }

  async function runCampaign(t: MessageTemplate) {
    if (!t.target_stage) {
      alert("This template has no target stage set.");
      return;
    }
    const inactiveDaysStr = prompt(
      `Send "${t.name}" to opted-in contacts currently at "${FUNNEL_STAGE_LABELS[t.target_stage]}" who haven't messaged in at least how many days?`,
      "3"
    );
    if (inactiveDaysStr === null) return;
    const inactiveDays = Math.max(0, Number(inactiveDaysStr) || 0);
    setCampaignBusy(t.id);
    setCampaignResult(null);
    try {
      const result = await sendRetargetCampaign({
        template_id: t.id,
        target_stage: t.target_stage,
        inactive_days: inactiveDays,
      });
      setCampaignResult(
        `"${t.name}": ${result.sent} sent, ${result.skipped_not_opted_in} skipped (not opted in), ` +
          `${result.failed} failed, out of ${result.matched} matching contacts.` +
          (result.remaining > 0
            ? ` ${result.remaining} more matched but weren't sent this batch (pacing cap) — run the campaign again to reach them.`
            : "")
      );
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Could not send this campaign.");
    } finally {
      setCampaignBusy(null);
    }
  }

  return (
    <div className="admin-panel">
      <div className="admin-panel-header admin-panel-header-row">
        <div>
          <h2>WhatsApp bot &amp; marketing funnel</h2>
          <p className="panel-sub">
            AIDA funnel stages, opt-in, and retargeting for the WhatsApp bot on your website.
          </p>
          {health && (
            <p className="panel-sub" style={{ marginTop: 4 }}>
              <span className={`pill ${health.whatsapp.ok ? "pill-active" : "pill-inactive"}`} title={health.whatsapp.detail}>
                WhatsApp: {health.whatsapp.configured ? (health.whatsapp.ok ? "Connected" : "Error") : "Not configured"}
              </span>{" "}
              <span className={`pill ${health.openrouter.ok ? "pill-active" : "pill-inactive"}`} title={health.openrouter.detail}>
                AI (OpenRouter): {health.openrouter.configured ? (health.openrouter.ok ? "Connected" : "Error") : "Not configured"}
              </span>
            </p>
          )}
        </div>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Select month" />
      </div>

      {alerts.length > 0 && (
        <div className="admin-card" style={{ borderLeft: "4px solid #c0392b", background: "#fdf1f0" }}>
          <h3 style={{ color: "#c0392b" }}>⚠️ {alerts.length} alert{alerts.length === 1 ? "" : "s"} need attention</h3>
          <p className="panel-sub">
            The AI bot flagged these WhatsApp messages as a possible emergency or an explicit request to talk
            to a person. Contact the patient directly if needed, then acknowledge.
          </p>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Phone</th>
                  <th>When</th>
                  <th>Message</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td>{a.phone}</td>
                    <td>{timeAgo(a.created_at)}</td>
                    <td style={{ maxWidth: 320 }}>{a.message_excerpt || "—"}</td>
                    <td>
                      <button className="btn-secondary btn-sm" onClick={() => handleAcknowledge(a.id)}>
                        Acknowledge
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {loading && <p className="panel-sub">Loading…</p>}
      {error && <p className="error-text">{error}</p>}

      {summary && !loading && (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="stat-value num">{summary.total_contacts}</div>
              <div className="stat-label">Total WhatsApp contacts</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{(summary.opted_in_rate * 100).toFixed(0)}%</div>
              <div className="stat-label">Opted in ({summary.opted_in})</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{summary.bookings_from_whatsapp}</div>
              <div className="stat-label">Bookings via WhatsApp this month</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value num">{summary.messages_in_range}</div>
              <div className="stat-label">Messages this month</div>
            </div>
          </div>

          <div className="report-grid">
            <div className="admin-card">
              <h3>Funnel — reached this stage this month</h3>
              <div className="bar-list">
                {STAGES.map((s) => (
                  <FunnelBar key={s} stage={s} value={summary.ever_reached_by_stage[s] ?? 0} max={maxFunnel} />
                ))}
              </div>
              <p className="panel-sub" style={{ marginTop: 10 }}>
                Stage-to-stage conversion this month:{" "}
                {STAGES.slice(1)
                  .map((s) => `${FUNNEL_STAGE_LABELS[s]} ${((summary.conversion_rates[s] ?? 0) * 100).toFixed(0)}%`)
                  .join(" · ")}
                . This is a range-level ratio (how many contacts who reached the previous stage also reached
                this one), not a per-contact cohort trace — a contact who jumped straight from Awareness to
                Action is counted at the deepest stage they reached.
              </p>
            </div>

            <div className="admin-card">
              <h3>Current stage (all contacts, live)</h3>
              <div className="bar-list">
                {STAGES.map((s) => (
                  <FunnelBar
                    key={s}
                    stage={s}
                    value={summary.current_by_stage[s] ?? 0}
                    max={Math.max(1, ...STAGES.map((x) => summary.current_by_stage[x] ?? 0))}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="admin-card">
            <h3>Contacts</h3>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Name / phone</th>
                    <th>Stage</th>
                    <th>Opted in</th>
                    <th>Last message</th>
                    <th>Linked patient</th>
                  </tr>
                </thead>
                <tbody>
                  {conversations.length === 0 && (
                    <tr>
                      <td colSpan={5} className="panel-sub">
                        No WhatsApp contacts yet.
                      </td>
                    </tr>
                  )}
                  {conversations.map((c) => (
                    <tr key={c.id}>
                      <td>{c.display_name || c.patient?.full_name || "—"} · {c.phone}</td>
                      <td>
                        <span className="pill" style={{ background: STAGE_COLORS[c.funnel_stage], color: "white" }}>
                          {FUNNEL_STAGE_LABELS[c.funnel_stage]}
                        </span>
                      </td>
                      <td>
                        <span className={`pill ${c.opted_in ? "pill-active" : "pill-inactive"}`}>
                          {c.opted_in ? "Yes" : "No"}
                        </span>
                      </td>
                      <td>{timeAgo(c.last_inbound_at)}</td>
                      <td>{c.patient ? c.patient.full_name : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="admin-card">
            <h3>Retargeting templates</h3>
            <p className="panel-sub">
              WhatsApp only allows marketing messages outside the 24-hour reply window using templates
              Meta has pre-approved. Draft one here, submit it in Meta Business Manager using the exact
              same text, then mark it Approved once Meta confirms — only then can it be sent as a campaign.
            </p>

            <div className="field-row">
              <div className="field">
                <label htmlFor="tpl_name">Internal name</label>
                <input
                  id="tpl_name"
                  value={tName}
                  onChange={(e) => setTName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
                  placeholder="e.g. desire_stage_nudge"
                />
              </div>
              <div className="field">
                <label htmlFor="tpl_category">Category</label>
                <select id="tpl_category" value={tCategory} onChange={(e) => setTCategory(e.target.value as TemplateCategory)}>
                  <option value="marketing">Marketing</option>
                  <option value="utility">Utility</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="tpl_stage">Target stage</label>
                <select id="tpl_stage" value={tStage} onChange={(e) => setTStage(e.target.value as FunnelStage)}>
                  {STAGES.filter((s) => s !== "booked").map((s) => (
                    <option key={s} value={s}>
                      {FUNNEL_STAGE_LABELS[s]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="tpl_body">Message body</label>
              <textarea
                id="tpl_body"
                value={tBody}
                onChange={(e) => setTBody(e.target.value)}
                rows={2}
                placeholder="Hi! We noticed you were exploring fertility consultations with us — happy to answer any questions or help you book. Reply anytime."
              />
            </div>
            <button className="btn-primary" onClick={handleCreateTemplate} disabled={savingTemplate}>
              {savingTemplate ? "Saving…" : "Save draft template"}
            </button>

            {campaignResult && <p className="panel-sub">{campaignResult}</p>}

            <div className="admin-table-wrap" style={{ marginTop: 16 }}>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Target stage</th>
                    <th>Status</th>
                    <th>Body</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {templates.length === 0 && (
                    <tr>
                      <td colSpan={5} className="panel-sub">
                        No templates yet.
                      </td>
                    </tr>
                  )}
                  {templates.map((t) => (
                    <tr key={t.id}>
                      <td>{t.name}</td>
                      <td>{t.target_stage ? FUNNEL_STAGE_LABELS[t.target_stage] : "—"}</td>
                      <td>
                        <span className={`pill status-${t.status === "approved" ? "confirmed" : t.status === "rejected" ? "cancelled" : "scheduled"}`}>
                          {t.status}
                        </span>
                      </td>
                      <td style={{ maxWidth: 280 }}>{t.body}</td>
                      <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {t.status === "draft" && (
                          <button className="btn-secondary btn-sm" onClick={() => markSubmitted(t)}>
                            Mark submitted
                          </button>
                        )}
                        {(t.status === "submitted" || t.status === "draft") && (
                          <button
                            className="btn-secondary btn-sm"
                            disabled={syncingId === t.id}
                            onClick={() => handleSyncStatus(t)}
                            title="Check the real status with Meta instead of setting it manually"
                          >
                            {syncingId === t.id ? "Checking…" : "Sync status"}
                          </button>
                        )}
                        {t.status === "submitted" && (
                          <button className="btn-secondary btn-sm" onClick={() => markApproved(t)}>
                            Mark approved
                          </button>
                        )}
                        {t.status === "approved" && (
                          <button
                            className="btn-primary btn-sm"
                            disabled={campaignBusy === t.id}
                            onClick={() => runCampaign(t)}
                          >
                            {campaignBusy === t.id ? "Sending…" : "Send campaign"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
