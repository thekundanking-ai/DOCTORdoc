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
    { path: "/patients", method: "POST", status: 201, body: {} },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 10 } },
  ]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("Full name"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("Mobile"), "+15559998877");
  await user.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => {
    const created = fetchMock.mock.calls.find(
      ([url, init]) => String(url) === "/api/patients" && init?.method === "POST"
    );
    expect(created).toBeTruthy();
  });
  expect(await screen.findByText("No patients found.")).toBeInTheDocument();
});

test("shows the server error (e.g. duplicate) on save", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", method: "POST", status: 409, body: { detail: "A patient with this name and mobile already exists" } },
  ]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("Full name"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("Mobile"), "+15559998877");
  await user.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByText("A patient with this name and mobile already exists")).toBeInTheDocument();
});

test("rejects invalid mobile with client-side validation before submitting", async () => {
  const fetchMock = installFetchMock([{ path: "/auth/me", status: 200, body: testUser() }]);
  renderAt("/patients/new");

  const user = userEvent.setup();
  await user.type(await screen.findByPlaceholderText("Full name"), "Carol Zhang");
  await user.type(await screen.findByPlaceholderText("Mobile"), "abc");
  await user.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByText(/valid name and mobile/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});
