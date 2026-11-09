import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ConsultationRecorderPage from "./ConsultationRecorderPage";
import { installFetchMock } from "../test/fetchMock";
import { installMediaMocks } from "../test/mediaMock";

const CONSULTATION = {
  id: 10,
  clinic_id: 1,
  patient_id: 5,
  created_by_user_id: 1,
  status: "open",
  started_at: "2026-11-06T00:00:00Z",
  ended_at: null,
  created_at: "2026-11-06T00:00:00Z",
  updated_at: "2026-11-06T00:00:00Z",
  audio: null,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/patients/5/consultations/new"]}>
      <Routes>
        <Route path="/patients/:id/consultations/new" element={<ConsultationRecorderPage />} />
        <Route path="/patients/:id" element={<div>PATIENT PAGE</div>} />
      </Routes>
    </MemoryRouter>
  );
}

test("requires consent, starts a consultation, records, and uploads", async () => {
  installMediaMocks();
  const fetchMock = installFetchMock([
    { path: "/patients/5", status: 200, body: { id: 5, full_name: "Alice Smith", mobile: "+15551234567", is_active: true, clinic_id: 1, created_by: 1 } },
    { path: "/consultations", method: "POST", status: 201, body: CONSULTATION },
    {
      path: "/consultations/10/audio",
      method: "POST",
      status: 201,
      body: {
        id: 9,
        consultation_id: 10,
        mime_type: "audio/webm",
        file_size_bytes: 3,
        duration_seconds: 2,
        uploaded_at: "",
        expires_at: "",
      },
    },
  ]);
  const user = userEvent.setup();
  renderPage();

  const continueButton = screen.getByRole("button", { name: "Continue" });
  expect(continueButton).toBeDisabled();

  await user.click(screen.getByRole("checkbox"));
  expect(continueButton).toBeEnabled();

  await user.click(continueButton);
  expect(await screen.findByRole("button", { name: "Start recording" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByText(/Recording…/);
  await user.click(screen.getByRole("button", { name: "Stop" }));
  await screen.findByTestId("preview-audio");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByText("PATIENT PAGE")).toBeInTheDocument();
  const uploaded = fetchMock.mock.calls.find(
    ([url, init]) => String(url) === "/api/consultations/10/audio" && init?.method === "POST"
  );
  expect(uploaded).toBeTruthy();
});
