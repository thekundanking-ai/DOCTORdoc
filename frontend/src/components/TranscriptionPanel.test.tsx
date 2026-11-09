import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import TranscriptionPanel from "./TranscriptionPanel";
import { installFetchMock } from "../test/fetchMock";

const CONSULTATION_ID = 7;

const COMPLETED = {
  id: 1,
  consultation_id: CONSULTATION_ID,
  clinic_id: 1,
  provider: "MockSpeechToTextProvider",
  provider_model: "prisma-v3.0",
  provider_job_id: "mock-job-1",
  status: "completed",
  language_code: "indic-auto",
  format: "transcribe",
  transcript_text: "this is a mock transcript",
  detected_language: "en-IN",
  processing_time_ms: 900,
  error_code: null,
  error_message: null,
  retry_count: 0,
  submitted_at: "2026-11-06T00:00:00Z",
  completed_at: "2026-11-06T00:01:00Z",
  created_at: "2026-11-06T00:00:00Z",
  updated_at: "2026-11-06T00:01:00Z",
};

function renderPanel() {
  return render(
    <MemoryRouter>
      <TranscriptionPanel consultationId={CONSULTATION_ID} hasAudio patientId={1} />
    </MemoryRouter>
  );
}

test("shows completed transcript with warning and report action", async () => {
  installFetchMock([{ path: `/consultations/${CONSULTATION_ID}/transcription`, status: 200, body: COMPLETED }]);
  renderPanel();

  expect(await screen.findByText("this is a mock transcript")).toBeInTheDocument();
  expect(screen.getByText(/Detected language: en-IN/)).toBeInTheDocument();
  expect(screen.getByText(/AI transcription may contain errors/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Generate Consultation Report/ })).toBeInTheDocument();
});

test("shows failed state and retry", async () => {
  const failed = { ...COMPLETED, status: "failed", transcript_text: null, error_code: "TRANSCRIPTION_FAILED", error_message: "The provider could not transcribe the audio." };
  const retried = { ...failed, status: "submitting", error_code: null, error_message: null };
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION_ID}/transcription`, status: 200, body: failed },
    { path: `/consultations/${CONSULTATION_ID}/transcription/retry`, method: "POST", status: 200, body: retried },
  ]);
  renderPanel();

  expect(await screen.findByText("The provider could not transcribe the audio.")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Submitting")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
});

test("polls while processing until completed", async () => {
  const processing = { ...COMPLETED, status: "processing", transcript_text: null, completed_at: null };
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION_ID}/transcription`, status: 200, body: [processing, COMPLETED] },
  ]);
  renderPanel();

  expect(await screen.findByText("Processing")).toBeInTheDocument();
  expect(await screen.findByText("this is a mock transcript", {}, { timeout: 4000 })).toBeInTheDocument();
  expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
});

test("requires confirmation before submitting transcription", async () => {
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION_ID}/transcription`, status: 404, body: { detail: "No transcription found" } },
    { path: `/consultations/${CONSULTATION_ID}/transcription`, method: "POST", status: 201, body: { ...COMPLETED, status: "submitting", transcript_text: null } },
  ]);
  renderPanel();

  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Transcribe audio" }));
  expect(screen.getByText(/sent to Gnani AI/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Confirm and submit" }));
  expect(await screen.findByText("Submitting")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
});

test("shows terminal processing-timeout state without retry", async () => {
  const timedOut = {
    ...COMPLETED,
    status: "failed",
    transcript_text: null,
    error_code: "PROCESSING_TIMEOUT",
    error_message: "Transcription exceeded the maximum allowed time.",
    provider_status: "IN_PROGRESS",
    poll_count: 501,
  };
  installFetchMock([{ path: `/consultations/${CONSULTATION_ID}/transcription`, status: 200, body: timedOut }]);
  renderPanel();

  expect(await screen.findByText("Transcription exceeded the maximum allowed time.")).toBeInTheDocument();
  expect(screen.getByText(/Last provider status: IN_PROGRESS/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
});
