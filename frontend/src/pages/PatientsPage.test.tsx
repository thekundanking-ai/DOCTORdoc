import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testPatient, testUser } from "../test/fetchMock";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

test("lists patients for the authenticated clinic", async () => {
  const fetchMock = installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    {
      path: "/patients",
      status: 200,
      body: { items: [testPatient(), testPatient({ id: 2, full_name: "Bob Brown" })], total: 2, page: 1, page_size: 10 },
    },
  ]);
  renderAt("/patients");

  expect(await screen.findByText("Alice Smith")).toBeInTheDocument();
  expect(await screen.findByText("Bob Brown")).toBeInTheDocument();
  expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/patients"))).toBe(true);
});

test("shows empty state when no patients exist", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 10 } },
  ]);
  renderAt("/patients");
  expect(await screen.findByText("No patients yet")).toBeInTheDocument();
});

test("shows error state when the list request fails", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", status: 500, body: { detail: "boom" } },
  ]);
  renderAt("/patients");
  expect(await screen.findByText("boom")).toBeInTheDocument();
});

test("search sends the query parameter to the API", async () => {
  const fetchMock = installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 10 } },
  ]);
  renderAt("/patients");
  await screen.findByText("No patients yet");

  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Search patients"), "Ali");
  await user.keyboard("{Enter}");

  await waitFor(() => {
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("q=Ali"))).toBe(true);
  });
});
