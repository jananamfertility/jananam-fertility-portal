import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Calendar,
  dateFnsLocalizer,
  type SlotInfo,
  type View,
  Views,
} from "react-big-calendar";
import { format, parse, startOfWeek, getDay } from "date-fns";
import { enUS } from "date-fns/locale";
import "react-big-calendar/lib/css/react-big-calendar.css";

import { fetchAppointments, fetchProviders } from "../lib/api";
import type { Appointment, Provider } from "../lib/types";
import { APPOINTMENT_STATUS_LABELS, APPOINTMENT_TYPE_LABELS } from "../lib/types";
import AppointmentModal from "../components/AppointmentModal";

const locales = { "en-US": enUS };
const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek: () => startOfWeek(new Date(), { weekStartsOn: 1 }),
  getDay,
  locales,
});

// Validated (dataviz skill) 3-slot categorical palette — reused across the
// calendar, the appointment form, and the admin reports charts.
const TYPE_COLORS: Record<string, string> = {
  consultation: "#1f8f61",
  follow_up: "#2a78d6",
  nt_scan: "#c94f86",
};

const STATUS_OPACITY: Record<string, number> = {
  scheduled: 1,
  confirmed: 1,
  completed: 0.55,
  no_show: 0.55,
  cancelled: 0.35,
};

interface CalEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  appointment: Appointment;
}

export default function CalendarPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [range, setRange] = useState<{ start: Date; end: Date }>(() => {
    const now = new Date();
    return {
      start: new Date(now.getFullYear(), now.getMonth(), 1),
      end: new Date(now.getFullYear(), now.getMonth() + 1, 1),
    };
  });
  const [view, setView] = useState<View>(Views.MONTH);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Appointment | null>(null);
  const [slot, setSlot] = useState<{ start: Date; end: Date } | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAppointments({
        start: range.start.toISOString(),
        end: range.end.toISOString(),
        providerId: providerFilter || undefined,
      });
      setAppointments(data);
    } finally {
      setLoading(false);
    }
  }, [range, providerFilter]);

  useEffect(() => {
    fetchProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const events: CalEvent[] = useMemo(
    () =>
      appointments.map((a) => ({
        id: a.id,
        title: `${a.patient?.full_name ?? "Patient"} — ${APPOINTMENT_TYPE_LABELS[a.appointment_type]}`,
        start: new Date(a.starts_at),
        end: new Date(a.ends_at),
        appointment: a,
      })),
    [appointments]
  );

  function handleSelectSlot(info: SlotInfo) {
    setEditing(null);
    setSlot({ start: info.start, end: info.end });
    setModalOpen(true);
  }

  function handleSelectEvent(event: CalEvent) {
    setEditing(event.appointment);
    setSlot(undefined);
    setModalOpen(true);
  }

  function handleRangeChange(newRange: Date[] | { start: Date; end: Date }) {
    if (Array.isArray(newRange)) {
      if (newRange.length === 0) return;
      setRange({
        start: newRange[0],
        end: new Date(newRange[newRange.length - 1].getTime() + 24 * 60 * 60 * 1000),
      });
    } else {
      setRange(newRange);
    }
  }

  function eventStyleGetter(event: CalEvent) {
    const color = TYPE_COLORS[event.appointment.appointment_type] ?? "#555";
    const opacity = STATUS_OPACITY[event.appointment.status] ?? 1;
    return {
      style: {
        backgroundColor: color,
        opacity,
        borderRadius: 6,
        border: "none",
        color: "white",
      },
    };
  }

  return (
    <div className="page-section">
      <div className="toolbar">
        <div className="nav-cluster">
          <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)}>
            <option value="">All providers</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <button
          className="btn-primary"
          onClick={() => {
            setEditing(null);
            setSlot(undefined);
            setModalOpen(true);
          }}
        >
          + New appointment
        </button>
      </div>

      <div className="legend">
        {Object.entries(APPOINTMENT_TYPE_LABELS).map(([key, label]) => (
          <span key={key} className="legend-item">
            <span className="legend-dot" style={{ background: TYPE_COLORS[key] }} />
            {label}
          </span>
        ))}
        {Object.entries(APPOINTMENT_STATUS_LABELS)
          .filter(([key]) => key === "completed" || key === "cancelled")
          .map(([key, label]) => (
            <span key={key} className="legend-item">
              <span className="legend-dot" style={{ background: "#555", opacity: STATUS_OPACITY[key] }} />
              {label} (faded)
            </span>
          ))}
      </div>

      <main className="calendar-wrap">
        {loading && <div className="loading-banner">Loading…</div>}
        <Calendar
          localizer={localizer}
          events={events}
          startAccessor="start"
          endAccessor="end"
          selectable
          view={view}
          onView={setView}
          views={[Views.MONTH, Views.WEEK, Views.DAY, Views.AGENDA]}
          onRangeChange={handleRangeChange}
          onSelectSlot={handleSelectSlot}
          onSelectEvent={handleSelectEvent}
          eventPropGetter={eventStyleGetter}
          style={{ height: "calc(100vh - 190px)" }}
          popup
        />
      </main>

      <AppointmentModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={() => {
          setModalOpen(false);
          load();
        }}
        providers={providers}
        appointment={editing}
        initialStart={slot?.start}
        initialEnd={slot?.end}
      />
    </div>
  );
}
