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

export type FunnelStage = "awareness" | "interest" | "desire" | "action" | "booked";

export const FUNNEL_STAGE_LABELS: Record<FunnelStage, string> = {
  awareness: "Awareness",
  interest: "Interest",
  desire: "Desire",
  action: "Action",
  booked: "Booked",
};

export type TemplateStatus = "draft" | "submitted" | "approved" | "rejected";
export type TemplateCategory = "marketing" | "utility";

export interface WhatsAppConversation {
  id: string;
  phone: string;
  display_name?: string | null;
  patient_id?: string | null;
  funnel_stage: FunnelStage;
  opted_in: boolean;
  opted_in_at?: string | null;
  last_inbound_at?: string | null;
  last_outbound_at?: string | null;
  created_at: string;
  patient?: Patient | null;
}

export interface FunnelSummary {
  range_start: string;
  range_end: string;
  total_contacts: number;
  current_by_stage: Record<string, number>;
  ever_reached_by_stage: Record<string, number>;
  opted_in: number;
  opted_in_rate: number;
  bookings_from_whatsapp: number;
  messages_in_range: number;
}

export interface MessageTemplate {
  id: string;
  name: string;
  category: TemplateCategory;
  body: string;
  variables: string[];
  target_stage?: FunnelStage | null;
  status: TemplateStatus;
  meta_template_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TemplateInput {
  name: string;
  category: TemplateCategory;
  body: string;
  variables: string[];
  target_stage?: FunnelStage | null;
}

export interface RetargetResult {
  matched: number;
  sent: number;
  skipped_not_opted_in: number;
  failed: number;
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
