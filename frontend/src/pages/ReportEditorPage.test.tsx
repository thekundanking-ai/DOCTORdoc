import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ReportEditorPage from "./ReportEditorPage";
import { ToastProvider } from "../components/ui/Toast";
import { installFetchMock } from "../test/fetchMock";

const CONSULTATION = 10;

const DRAFT_REPORT = {
  id: 1,
  consultation_id: CONSULTATION,
  clinic_id: 1,
  patient_id: 1,
  status: "generated",
  provider: "MockReportProvider",
  model: "mock",
  structured_report: {
    patient_information: { name: "Alice Smith", mobile: "+15551234567", consultation_date: "2026-11-06" },
    chief_complaint: "Fever and sore throat",
    symptoms: ["fever", "sore throat"],
    medical_history: null,
    clinical_observations: null,
    diagnosis: "Upper respiratory tract infection",
    medications: [{ name: "Paracetamol", dosage: "500 mg", frequency: "as needed", duration: "3 days" }],
    investigations: null,
    treatment_and_advice: "Hydration and rest",
    follow_up: "Review in 3 days",
    unclear_or_missing: [],
  },
  error_code: null,
  error_message: null,
  approved_at: null,
  approved_by: null,
  created_at: "2026-11-06T00:00:00Z",
  updated_at: "2026-11-06T00:00:00Z",
};

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={["/patients/1/consultations/10/report"]}>
        <Routes>
          <Route path="/patients/:id/consultations/:cid/report" element={<ReportEditorPage />} />
          <Route path="/patients/:id" element={<div>PATIENT PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>
  );
}

test("shows editable draft and saves changes", async () => {
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION}/report`, status: 200, body: DRAFT_REPORT },
    { path: `/consultations/${CONSULTATION}/report`, method: "PATCH", status: 200, body: { ...DRAFT_REPORT, status: "draft" } },
  ]);
  renderPage();

  const complaint = await screen.findByLabelText("Chief complaint");
  expect((complaint as HTMLInputElement).value).toBe("Fever and sore throat");

  const user = userEvent.setup();
  await user.clear(complaint);
  await user.type(complaint, "Cough and runny nose");
  await user.click(screen.getByRole("button", { name: "Save Draft" }));

  expect(await screen.findByText("Draft saved")).toBeInTheDocument();
  const patched = fetchMock.mock.calls.find(([url, init]) => String(url) === `/api/consultations/${CONSULTATION}/report` && init?.method === "PATCH");
  expect(patched).toBeTruthy();
});

test("approve requires confirmation and records approval", async () => {
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION}/report`, status: 200, body: DRAFT_REPORT },
    {
      path: `/consultations/${CONSULTATION}/report/approve`,
      method: "POST",
      status: 200,
      body: { ...DRAFT_REPORT, status: "approved", approved_by: 1, approved_at: "2026-11-06T00:10:00Z" },
    },
  ]);
  renderPage();
  await screen.findByLabelText("Chief complaint");

  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Approve" }));
  expect(screen.getByText(/Approve report\?/)).toBeInTheDocument();
  const confirmButtons = screen.getAllByRole("button", { name: "Approve" });
  await user.click(confirmButtons[confirmButtons.length - 1]);

  expect(await screen.findByText(/Approved by user #1/)).toBeInTheDocument();
  const approved = fetchMock.mock.calls.find(([url, init]) => String(url) === `/api/consultations/${CONSULTATION}/report/approve` && init?.method === "POST");
  expect(approved).toBeTruthy();
});

test("shows review warnings when required", async () => {
  const withGaps = {
    ...DRAFT_REPORT,
    structured_report: {
      ...DRAFT_REPORT.structured_report,
      diagnosis: null,
      unclear_or_missing: ["Dose for Paracetamol unclear"],
    },
  };
  installFetchMock([{ path: `/consultations/${CONSULTATION}/report`, status: 200, body: withGaps }]);
  renderPage();

  expect(await screen.findByText(/No diagnosis recorded/)).toBeInTheDocument();
  expect(screen.getAllByText(/Dose for Paracetamol unclear/).length).toBeGreaterThan(0);
});

test("show failed state and allows retry generation", async () => {
  const failedReport = { ...DRAFT_REPORT, status: "failed", structured_report: null, error_message: "Report generation failed. You can retry." };
  const generated = { ...DRAFT_REPORT, status: "generated" };
  const fetchMock = installFetchMock([
    { path: `/consultations/${CONSULTATION}/report`, status: 200, body: failedReport },
    { path: `/consultations/${CONSULTATION}/report/generate`, method: "POST", status: 200, body: generated },
  ]);
  renderPage();
  expect((await screen.findAllByText(/Report generation failed/)).length).toBeGreaterThan(0);

  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByDisplayValue("Fever and sore throat")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true);
});
