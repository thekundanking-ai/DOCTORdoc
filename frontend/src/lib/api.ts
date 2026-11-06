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
};
