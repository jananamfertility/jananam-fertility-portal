export type AppointmentType = "consultation" | "follow_up" | "nt_scan";

export type AppointmentStatus =
  | "scheduled"
  | "confirmed"
  | "completed"
  | "no_show"
  | "cancelled";

export type AppointmentSource = "manual" | "whatsapp";

export const APPOINTMENT_TYPE_LABELS: Record<AppointmentType, string> = {
  consultation: "Consultation",
  follow_up: "Follow-up",
  nt_scan: "NT Scan",
};

export const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled",
  confirmed: "Confirmed",
  completed: "Completed",
  no_show: "No-show",
  cancelled: "Cancelled",
};

export interface Provider {
  id: string;
  name: string;
  designation?: string | null;
  is_active: boolean;
}

export interface Patient {
  id: string;
  full_name: string;
  phone: string;
  age?: number | null;
  partner_name?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PatientInput {
  full_name: string;
  phone: string;
  age?: number | null;
  partner_name?: string | null;
  notes?: string | null;
}

export interface Appointment {
  id: string;
  patient_id: string;
  provider_id?: string | null;
  appointment_type: AppointmentType;
  status: AppointmentStatus;
  starts_at: string;
  ends_at: string;
  notes?: string | null;
  source: AppointmentSource;
  whatsapp_message_id?: string | null;
  created_at: string;
  updated_at: string;
  patient?: Patient | null;
  provider?: Provider | null;
}

export interface AppointmentInput {
  patient_id?: string;
  patient?: PatientInput;
  provider_id?: string | null;
  appointment_type: AppointmentType;
  status: AppointmentStatus;
  starts_at: string;
  ends_at: string;
  notes?: string | null;
}

export type StaffRole = "front_office" | "admin";

export interface StaffProfile {
  id: string;
  email?: string | null;
  full_name: string;
  role: StaffRole;
  is_active: boolean;
}

export interface StaffAccount extends StaffProfile {
  created_at: string;
}

export interface StaffCreateInput {
  email: string;
  full_name: string;
  password: string;
  role: StaffRole;
}

export interface ReportSummary {
  range_start: string;
  range_end: string;
  total: number;
  kept: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  by_weekday: Record<string, number>;
  by_provider: Record<string, number>;
  no_show_rate: number;
  cancellation_rate: number;
}
