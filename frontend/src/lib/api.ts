import axios from "axios";
import { supabase } from "./supabaseClient";
import type {
  Appointment,
  AppointmentInput,
  FunnelSummary,
  MessageTemplate,
  Patient,
  PatientInput,
  Provider,
  ReportSummary,
  RetargetResult,
  StaffAccount,
  StaffCreateInput,
  StaffProfile,
  TemplateInput,
  WhatsAppConversation,
} from "./types";

const baseURL = import.meta.env.VITE_API_BASE_URL as string;

export const api = axios.create({ baseURL });

// Attach the current Supabase session's access token to every request, so
// the FastAPI backend can verify who is calling.
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function fetchAppointments(params: {
  start: string;
  end: string;
  providerId?: string;
}): Promise<Appointment[]> {
  const { data } = await api.get<Appointment[]>("/api/appointments", {
    params: { start: params.start, end: params.end, provider_id: params.providerId },
  });
  return data;
}

export async function createAppointment(payload: AppointmentInput): Promise<Appointment> {
  const { data } = await api.post<Appointment>("/api/appointments", payload);
  return data;
}

export async function updateAppointment(
  id: string,
  payload: Partial<AppointmentInput>
): Promise<Appointment> {
  const { data } = await api.patch<Appointment>(`/api/appointments/${id}`, payload);
  return data;
}

export async function deleteAppointment(id: string): Promise<void> {
  await api.delete(`/api/appointments/${id}`);
}

export async function fetchProviders(includeInactive = false): Promise<Provider[]> {
  const { data } = await api.get<Provider[]>("/api/providers", {
    params: { include_inactive: includeInactive },
  });
  return data;
}

export async function createProvider(payload: {
  name: string;
  designation?: string | null;
  is_active?: boolean;
}): Promise<Provider> {
  const { data } = await api.post<Provider>("/api/providers", payload);
  return data;
}

export async function updateProvider(
  id: string,
  payload: { name: string; designation?: string | null; is_active: boolean }
): Promise<Provider> {
  const { data } = await api.patch<Provider>(`/api/providers/${id}`, payload);
  return data;
}

export async function searchPatients(search: string): Promise<Patient[]> {
  const { data } = await api.get<Patient[]>("/api/patients", { params: { search } });
  return data;
}

export async function updatePatient(id: string, payload: PatientInput): Promise<Patient> {
  const { data } = await api.patch<Patient>(`/api/patients/${id}`, payload);
  return data;
}

export async function fetchMe(): Promise<StaffProfile> {
  const { data } = await api.get<StaffProfile>("/api/me");
  return data;
}

export async function fetchStaff(): Promise<StaffAccount[]> {
  const { data } = await api.get<StaffAccount[]>("/api/staff");
  return data;
}

export async function createStaff(payload: StaffCreateInput): Promise<StaffAccount> {
  const { data } = await api.post<StaffAccount>("/api/staff", payload);
  return data;
}

export async function updateStaff(
  id: string,
  payload: Partial<Pick<StaffAccount, "full_name" | "role" | "is_active">>
): Promise<StaffAccount> {
  const { data } = await api.patch<StaffAccount>(`/api/staff/${id}`, payload);
  return data;
}

export async function fetchReportSummary(params: {
  start: string;
  end: string;
}): Promise<ReportSummary> {
  const { data } = await api.get<ReportSummary>("/api/reports/summary", { params });
  return data;
}

// ---------------------------------------------------------------------------
// Marketing (WhatsApp bot / AIDA funnel) — admin panel
// ---------------------------------------------------------------------------
export async function fetchFunnelSummary(params: { start: string; end: string }): Promise<FunnelSummary> {
  const { data } = await api.get<FunnelSummary>("/api/marketing/funnel-summary", { params });
  return data;
}

export async function fetchConversations(params?: {
  stage?: string;
  opted_in?: boolean;
}): Promise<WhatsAppConversation[]> {
  const { data } = await api.get<WhatsAppConversation[]>("/api/marketing/conversations", { params });
  return data;
}

export async function fetchTemplates(): Promise<MessageTemplate[]> {
  const { data } = await api.get<MessageTemplate[]>("/api/marketing/templates");
  return data;
}

export async function createTemplate(payload: TemplateInput): Promise<MessageTemplate> {
  const { data } = await api.post<MessageTemplate>("/api/marketing/templates", payload);
  return data;
}

export async function updateTemplate(
  id: string,
  payload: Partial<Pick<MessageTemplate, "body" | "variables" | "target_stage" | "status" | "meta_template_name">>
): Promise<MessageTemplate> {
  const { data } = await api.patch<MessageTemplate>(`/api/marketing/templates/${id}`, payload);
  return data;
}

export async function sendRetargetCampaign(payload: {
  template_id: string;
  target_stage: string;
  inactive_days: number;
}): Promise<RetargetResult> {
  const { data } = await api.post<RetargetResult>("/api/marketing/retarget", payload);
  return data;
}
