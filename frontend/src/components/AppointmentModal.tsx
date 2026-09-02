import { useEffect, useMemo, useState } from "react";
import {
  createAppointment,
  deleteAppointment,
  searchPatients,
  updateAppointment,
  updatePatient,
} from "../lib/api";
import type {
  Appointment,
  AppointmentStatus,
  AppointmentType,
  Patient,
  Provider,
} from "../lib/types";
import { APPOINTMENT_STATUS_LABELS, APPOINTMENT_TYPE_LABELS } from "../lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  providers: Provider[];
  /** Existing appointment to edit, or null to create a new one. */
  appointment: Appointment | null;
  /** Pre-filled start time when creating from a calendar slot click. */
  initialStart?: Date;
  initialEnd?: Date;
}

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function toTimeInput(d: Date): string {
  return d.toISOString().slice(11, 16);
}
function combine(dateStr: string, timeStr: string): Date {
  return new Date(`${dateStr}T${timeStr}:00`);
}

const DEFAULT_DURATION_MIN: Record<AppointmentType, number> = {
  consultation: 30,
  follow_up: 20,
  nt_scan: 45,
};

export default function AppointmentModal({
  open,
  onClose,
  onSaved,
  providers,
  appointment,
  initialStart,
  initialEnd,
}: Props) {
  const isEditing = !!appointment;

  const startSeed = appointment ? new Date(appointment.starts_at) : initialStart ?? new Date();
  const endSeed = appointment
    ? new Date(appointment.ends_at)
    : initialEnd ?? new Date(startSeed.getTime() + 30 * 60000);

  const [fullName, setFullName] = useState(appointment?.patient?.full_name ?? "");
  const [phone, setPhone] = useState(appointment?.patient?.phone ?? "");
  const [age, setAge] = useState(appointment?.patient?.age?.toString() ?? "");
  const [partnerName, setPartnerName] = useState(appointment?.patient?.partner_name ?? "");
  const [patientNotes, setPatientNotes] = useState(appointment?.patient?.notes ?? "");

  const [providerId, setProviderId] = useState(appointment?.provider_id ?? providers[0]?.id ?? "");
  const [appointmentType, setAppointmentType] = useState<AppointmentType>(
    appointment?.appointment_type ?? "consultation"
  );
  const [appointmentStatus, setAppointmentStatus] = useState<AppointmentStatus>(
    appointment?.status ?? "scheduled"
  );
  const [date, setDate] = useState(toDateInput(startSeed));
  const [startTime, setStartTime] = useState(toTimeInput(startSeed));
  const [endTime, setEndTime] = useState(toTimeInput(endSeed));
  const [notes, setNotes] = useState(appointment?.notes ?? "");

  const [matches, setMatches] = useState<Patient[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When switching to a new appointment type, nudge the end time to a sane
  // default duration (only while creating — don't clobber an edit in place).
  useEffect(() => {
    if (isEditing) return;
    const start = combine(date, startTime);
    const end = new Date(start.getTime() + DEFAULT_DURATION_MIN[appointmentType] * 60000);
    setEndTime(toTimeInput(end));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointmentType]);

  useEffect(() => {
    if (isEditing || phone.length < 4) {
      setMatches([]);
      return;
    }
    const handle = setTimeout(async () => {
      try {
        const results = await searchPatients(phone);
        setMatches(results);
      } catch {
        setMatches([]);
      }
    }, 300);
    return () => clearTimeout(handle);
  }, [phone, isEditing]);

  function applyMatch(p: Patient) {
    setFullName(p.full_name);
    setPhone(p.phone);
    setAge(p.age?.toString() ?? "");
    setPartnerName(p.partner_name ?? "");
    setPatientNotes(p.notes ?? "");
    setMatches([]);
  }

  const startsAt = useMemo(() => combine(date, startTime), [date, startTime]);
  const endsAt = useMemo(() => combine(date, endTime), [date, endTime]);

  if (!open) return null;

  async function handleSave() {
    setError(null);
    if (!fullName.trim() || !phone.trim()) {
      setError("Patient name and phone are required.");
      return;
    }
    if (endsAt <= startsAt) {
      setError("End time must be after start time.");
      return;
    }

    setSaving(true);
    try {
      const patientPayload = {
        full_name: fullName.trim(),
        phone: phone.trim(),
        age: age ? Number(age) : null,
        partner_name: partnerName.trim() || null,
        notes: patientNotes.trim() || null,
      };

      if (isEditing && appointment) {
        if (appointment.patient_id) {
          await updatePatient(appointment.patient_id, patientPayload);
        }
        await updateAppointment(appointment.id, {
          patient_id: appointment.patient_id,
          provider_id: providerId || null,
          appointment_type: appointmentType,
          status: appointmentStatus,
          starts_at: startsAt.toISOString(),
          ends_at: endsAt.toISOString(),
          notes: notes.trim() || null,
        });
      } else {
        await createAppointment({
          patient: patientPayload,
          provider_id: providerId || null,
          appointment_type: appointmentType,
          status: appointmentStatus,
          starts_at: startsAt.toISOString(),
          ends_at: endsAt.toISOString(),
          notes: notes.trim() || null,
        });
      }
      onSaved();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!appointment) return;
    if (!confirm(`Delete this appointment for ${appointment.patient?.full_name ?? "this patient"}?`)) {
      return;
    }
    setSaving(true);
    try {
      await deleteAppointment(appointment.id);
      onSaved();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Could not delete this appointment.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isEditing ? "Edit appointment" : "New appointment"}</h2>

        <div className="modal-section">
          <h3>Patient</h3>
          <div className="field-row">
            <div className="field">
              <label>Phone</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="98765 43210" />
              {matches.length > 0 && (
                <ul className="match-list">
                  {matches.map((m) => (
                    <li key={m.id} onClick={() => applyMatch(m)}>
                      {m.full_name} — {m.phone}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="field">
              <label>Full name</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Age</label>
              <input value={age} onChange={(e) => setAge(e.target.value)} inputMode="numeric" />
            </div>
            <div className="field">
              <label>Partner name</label>
              <input value={partnerName} onChange={(e) => setPartnerName(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Patient notes</label>
            <textarea value={patientNotes} onChange={(e) => setPatientNotes(e.target.value)} rows={2} />
          </div>
        </div>

        <div className="modal-section">
          <h3>Appointment</h3>
          <div className="field-row">
            <div className="field">
              <label>Type</label>
              <select
                value={appointmentType}
                onChange={(e) => setAppointmentType(e.target.value as AppointmentType)}
              >
                {Object.entries(APPOINTMENT_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Provider</label>
              <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                <option value="">Unassigned</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.designation ? ` (${p.designation})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Status</label>
              <select
                value={appointmentStatus}
                onChange={(e) => setAppointmentStatus(e.target.value as AppointmentStatus)}
              >
                {Object.entries(APPOINTMENT_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label>Date</label>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="field">
              <label>Start</label>
              <input
                type="time"
                step={900}
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
            <div className="field">
              <label>End</label>
              <input
                type="time"
                step={900}
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label>Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </div>
        </div>

        {error && <p className="error-text">{error}</p>}

        <div className="modal-actions">
          {isEditing && (
            <button className="btn-danger" onClick={handleDelete} disabled={saving}>
              Delete
            </button>
          )}
          <div className="spacer" />
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
