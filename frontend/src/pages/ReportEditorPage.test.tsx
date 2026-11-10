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


test("sends approved report, disables button, and shows delivery history", async () => {
  const approvedReport = { ...DRAFT_REPORT, status: "approved", approved_by: 1, approved_at: "2026-11-06T00:10:00Z" };
  const delivery = {
    id: 1, report_id: 1, clinic_id: 1, channel: "email", status: "sent",
    recipient: "patient@example.com", error_message: null,
    delivered_at: "2026-11-06T00:11:00Z", created_at: "2026-11-06T00:11:00Z",
  };
  installFetchMock([
    { path: `/consultations/${CONSULTATION}/report`, status: 200, body: approvedReport },
    { path: `/consultations/${CONSULTATION}/report/deliver`, method: "POST", status: 200, body: delivery },
    { path: `/consultations/${CONSULTATION}/report/deliveries`, status: 200, body: [[], [delivery]] },
  ]);
  renderPage();

  await screen.findByText(/Approved by user #1/);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Send Report" }));

  expect(await screen.findByText("Report sent to patient")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Report sent" })).toBeDisabled();
  expect(await screen.findByText(/Sent via SMTP/)).toBeInTheDocument();
  expect(screen.getByText(/Recipient: patient@example.com/)).toBeInTheDocument();
});

test("shows safe failure feedback and allows retry", async () => {
  const approvedReport = { ...DRAFT_REPORT, status: "approved", approved_by: 1, approved_at: "2026-11-06T00:10:00Z" };
  const failedDelivery = {
    id: 2, report_id: 1, clinic_id: 1, channel: "email", status: "failed",
    recipient: "patient@example.com", error_message: "SMTP error: Connection refused",
    delivered_at: null, created_at: "2026-11-06T00:12:00Z",
  };
  installFetchMock([
    { path: `/consultations/${CONSULTATION}/report`, status: 200, body: approvedReport },
    { path: `/consultations/${CONSULTATION}/report/deliver`, method: "POST", status: 200, body: failedDelivery },
    { path: `/consultations/${CONSULTATION}/report/deliveries`, status: 200, body: [[], [failedDelivery]] },
  ]);
  renderPage();

  await screen.findByText(/Approved by user #1/);
  await userEvent.setup().click(screen.getByRole("button", { name: "Send Report" }));

  expect(await screen.findByText("Delivery failed")).toBeInTheDocument();
  expect(await screen.findByText(/Connection refused/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send Report" })).not.toBeDisabled();
});
