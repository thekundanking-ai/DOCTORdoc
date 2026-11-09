import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testUser } from "../test/fetchMock";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

test("creates a patient and navigates to the list", async () => {
  const fetchMock = installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", method: "POST", status: 201, body: { id: 9, full_name: "Carol Zhang", mobile: "+15559998877", is_active: true, clinic_id: 1, created_by: 1 } },
    { path: "/patients/9", status: 200, body: { id: 9, full_name: "Carol Zhang", mobile: "+15559998877", is_active: true, clinic_id: 1, created_by: 1 } },
    { path: "/consultations", status: 200, body: { items: [], total: 0, page: 1, page_size: 50 } },
  ]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("e.g. Ramesh Iyer"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("+91 98450 12345"), "+15559998877");
  await user.click(screen.getByRole("button", { name: "Add patient" }));

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(([url, init]) => String(url) === "/api/patients" && init?.method === "POST")
    ).toBe(true);
  });
  expect(await screen.findByText("No consultations yet")).toBeInTheDocument();
});

test("shows the server error (e.g. duplicate) on save", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", method: "POST", status: 409, body: { detail: "A patient with this name and mobile already exists" } },
  ]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("e.g. Ramesh Iyer"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("+91 98450 12345"), "+15559998877");
  await user.click(screen.getByRole("button", { name: "Add patient" }));

  expect(await screen.findByText("A patient with this name and mobile already exists")).toBeInTheDocument();
});

test("rejects invalid mobile with client-side validation before submitting", async () => {
  const fetchMock = installFetchMock([{ path: "/auth/me", status: 200, body: testUser() }]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("e.g. Ramesh Iyer"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("+91 98450 12345"), "abc");
  await user.click(screen.getByRole("button", { name: "Add patient" }));

  expect(await screen.findByText(/valid mobile number/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});
