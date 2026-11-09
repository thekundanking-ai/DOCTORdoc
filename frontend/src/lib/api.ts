export type User = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  clinic_id: number;
};

type ApiResult<T> = { ok: true; data: T };

async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
    credentials: "include",
  });

  let data: any = null;
  try {
    data = await response.json();
  } catch {
    /* empty body */
  }

  if (!response.ok) {
    const message = data?.detail || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return { ok: true, data };
}

export type Patient = {
  id: number;
  clinic_id: number;
  full_name: string;
  mobile: string;
  is_active: boolean;
  created_by: number;
  created_at: string;
  updated_at: string;
};

export type PatientListResult = {
  items: Patient[];
  total: number;
  page: number;
  page_size: number;
};

export type PatientInput = { full_name: string; mobile: string };
export type PatientPatch = Partial<PatientInput> & { is_active?: boolean };

export type PatientListParams = {
  q?: string;
  include_archived?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
  order?: string;
};

function querystring(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export type ConsultationStatus = "open" | "awaiting_transcription" | "completed" | "cancelled";

export type AudioAttachment = {
  id: number;
  consultation_id: number;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  uploaded_at: string;
  expires_at: string;
};

export type Consultation = {
  id: number;
  clinic_id: number;
  patient_id: number;
  created_by_user_id: number;
  status: ConsultationStatus;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  audio: AudioAttachment | null;
};

export type ConsultationListResult = {
  items: Consultation[];
  total: number;
  page: number;
  page_size: number;
};

export type TranscriptionStatus = "not_started" | "submitting" | "processing" | "completed" | "failed";

export type Transcription = {
  id: number;
  consultation_id: number;
  clinic_id: number;
  provider: string;
  provider_model: string;
  provider_job_id: string | null;
  status: TranscriptionStatus;
  language_code: string;
  format: string;
  transcript_text: string | null;
  detected_language: string | null;
  processing_time_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  retry_count: number;
  provider_status: string | null;
  poll_count: number;
  deadline_at: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

async function rawFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, credentials: "include" });
  let data: any = null;
  try {
    data = await response.json();
  } catch {
    /* empty body */
  }
  if (!response.ok) {
    throw new Error(data?.detail || `Request failed (${response.status})`);
  }
  return data as T;
}

export type ReportStatus = "generating" | "draft" | "generated" | "failed" | "approved";

export type MedicationItem = {
  name: string | null;
  dosage: string | null;
  frequency: string | null;
  duration: string | null;
};

export type ReportStructured = {
  patient_information?: { name: string | null; mobile: string | null; consultation_date: string | null } | null;
  chief_complaint?: string | null;
  symptoms?: string[] | null;
  medical_history?: string | null;
  clinical_observations?: string[] | null;
  diagnosis?: string | null;
  medications?: MedicationItem[] | null;
  investigations?: string[] | null;
  treatment_and_advice?: string | null;
  follow_up?: string | null;
  unclear_or_missing?: string[] | null;
};

export type Report = {
  id: number;
  consultation_id: number;
  clinic_id: number;
  patient_id: number;
  status: ReportStatus;
  provider: string;
  model: string;
  structured_report: ReportStructured | null;
  error_code: string | null;
  error_message: string | null;
  approved_at: string | null;
  approved_by: number | null;
  created_at: string;
  updated_at: string;
};

export type Delivery = {
  id: number;
  report_id: number;
  clinic_id: number;
  channel: string;
  status: "pending" | "sent" | "failed";
  error_message: string | null;
  delivered_at: string | null;
  created_at: string;
};

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) =>
    request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  patients: {
    list: (params: PatientListParams = {}) => request<PatientListResult>(`/patients${querystring(params)}`),
    get: (id: number) => request<Patient>(`/patients/${id}`),
    create: (data: PatientInput) => request<Patient>("/patients", { method: "POST", body: JSON.stringify(data) }),
    update: (id: number, data: PatientPatch) =>
      request<Patient>(`/patients/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    archive: (id: number) => request<Patient>(`/patients/${id}/archive`, { method: "POST" }),
  },
  consultations: {
    create: (patientId: number) =>
      request<Consultation>("/consultations", { method: "POST", body: JSON.stringify({ patient_id: patientId }) }),
    list: (patientId: number, params: { page?: number; page_size?: number } = {}) =>
      request<ConsultationListResult>(`/consultations${querystring({ patient_id: patientId, ...params })}`),
    get: (id: number) => request<Consultation>(`/consultations/${id}`),
    cancel: (id: number) => request<Consultation>(`/consultations/${id}/cancel`, { method: "POST" }),
    uploadAudio: (id: number, blob: Blob, uploadId: string, durationSeconds?: number) => {
      const form = new FormData();
      form.append("upload_id", uploadId);
      form.append("file", blob, `recording.${blob.type.split("/")[1] || "bin"}`);
      if (durationSeconds !== undefined) form.append("duration_seconds", String(durationSeconds));
      return rawFetch<AudioAttachment>(`/consultations/${id}/audio`, { method: "POST", body: form });
    },
    fetchAudioBlob: async (id: number): Promise<Blob> => {
      const response = await fetch(`/api/consultations/${id}/audio`, { credentials: "include" });
      if (!response.ok) {
        let data: any = null;
        try {
          data = await response.json();
        } catch {
          /* ignore */
        }
        throw new Error(data?.detail || `Request failed (${response.status})`);
      }
      return response.blob();
    },
  },
  transcriptions: {
    start: (consultationId: number) =>
      request<Transcription>(`/consultations/${consultationId}/transcription`, { method: "POST" }),
    get: (consultationId: number) => request<Transcription>(`/consultations/${consultationId}/transcription`),
    retry: (consultationId: number) =>
      request<Transcription>(`/consultations/${consultationId}/transcription/retry`, { method: "POST" }),
  },
  reports: {
    generate: (consultationId: number) =>
      request<Report>(`/consultations/${consultationId}/report/generate`, { method: "POST" }),
    get: (consultationId: number) => request<Report>(`/consultations/${consultationId}/report`),
    update: (consultationId: number, data: ReportStructured) =>
      request<Report>(`/consultations/${consultationId}/report`, { method: "PATCH", body: JSON.stringify(data) }),
    approve: (consultationId: number) =>
      request<Report>(`/consultations/${consultationId}/report/approve`, { method: "POST" }),
    downloadPdf: async (consultationId: number): Promise<Blob> => {
      const response = await fetch(`/api/consultations/${consultationId}/report/pdf`, { credentials: "include" });
      if (!response.ok) {
        let data: any = null;
        try {
          data = await response.json();
        } catch {
          /* ignore */
        }
        throw new Error(data?.detail || `Request failed (${response.status})`);
      }
      return response.blob();
    },
    deliver: (consultationId: number) =>
      request<Delivery>(`/consultations/${consultationId}/report/deliver`, { method: "POST" }),
  },
};
