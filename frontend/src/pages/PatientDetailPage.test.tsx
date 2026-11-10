import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testPatient } from "../test/fetchMock";

const PATIENT = testPatient({ id: 5 });
const CONSULTATION = {
  id: 10,
  clinic_id: 1,
  patient_id: 5,
  created_by_user_id: 1,
  status: "awaiting_transcription",
  started_at: "2026-11-06T00:00:00Z",
  ended_at: null,
  created_at: "2026-11-06T00:00:00Z",
  updated_at: "2026-11-06T00:00:00Z",
  audio: {
    id: 9,
    consultation_id: 10,
    mime_type: "audio/webm",
    file_size_bytes: 3,
    duration_seconds: 2,
    uploaded_at: "2026-11-06T00:00:00Z",
    expires_at: "2026-11-13T00:00:00Z",
  },
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/patients/5"]}>
      <App />
    </MemoryRouter>
  );
}

test("shows patient detail with consultation history", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: { id: 1, email: "owner@example.com", full_name: "Owner", role: "clinic_owner", clinic_id: 1 } },
    { path: "/patients/5", status: 200, body: PATIENT },
    { path: "/consultations", status: 200, body: { items: [CONSULTATION], total: 1, page: 1, page_size: 50 } },
    { path: "/consultations/10/transcription", status: 404, body: { detail: "No transcription found" } },
  ]);
  renderPage();

  expect(await screen.findByText("Alice Smith")).toBeInTheDocument();
  expect(screen.getByText("Consultations")).toBeInTheDocument();
  expect(screen.getByText("Start consultation")).toBeInTheDocument();
  expect(screen.getByText("awaiting transcription")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: /Transcribe/i })).toBeInTheDocument();
});

test("shows empty history state when none exist", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: { id: 1, email: "owner@example.com", full_name: "Owner", role: "clinic_owner", clinic_id: 1 } },
    { path: "/patients/5", status: 200, body: PATIENT },
    { path: "/consultations", status: 200, body: { items: [], total: 0, page: 1, page_size: 50 } },
  ]);
  renderPage();

  expect(await screen.findByText("No consultations yet")).toBeInTheDocument();
});

test("shows transcript for a completed consultation even when audio was deleted", async () => {
  const completed = { ...CONSULTATION, status: "completed", audio: null };
  const transcription = {
    id: 1,
    consultation_id: 10,
    clinic_id: 1,
    provider: "MockSpeechToTextProvider",
    provider_model: "prisma-v3.0",
    provider_job_id: "j",
    status: "completed",
    language_code: "indic-auto",
    format: "transcribe",
    transcript_text: "this is the persisted transcript",
    detected_language: "en-IN",
    processing_time_ms: 900,
    error_code: null,
    error_message: null,
    retry_count: 0,
    provider_status: null,
    poll_count: 2,
    deadline_at: null,
    submitted_at: "2026-11-06T00:00:00Z",
    completed_at: "2026-11-06T00:01:00Z",
    created_at: "2026-11-06T00:00:00Z",
    updated_at: "2026-11-06T00:01:00Z",
  };
  installFetchMock([
    { path: "/auth/me", status: 200, body: { id: 1, email: "owner@example.com", full_name: "Owner", role: "clinic_owner", clinic_id: 1 } },
    { path: "/patients/5", status: 200, body: PATIENT },
    { path: "/consultations", status: 200, body: { items: [completed], total: 1, page: 1, page_size: 50 } },
    { path: "/consultations/10/transcription", status: 200, body: transcription },
  ]);
  renderPage();

  expect(await screen.findByText("this is the persisted transcript")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Generate Consultation Report/ })).toBeInTheDocument();
});
