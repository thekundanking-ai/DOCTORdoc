import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testUser } from "../test/fetchMock";

test("allows access to protected route when authenticated", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 5 } },
  ]);
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>
  );
  expect(await screen.findByText("Add a patient")).toBeInTheDocument();
});

test("logout clears session and returns to login", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 5 } },
    { path: "/auth/logout", status: 200, body: { ok: true } },
  ]);
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>
  );
  await screen.findByText("Add a patient");

  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Dr. Anitha Rao" }));
  const logoutButtons = await screen.findAllByRole("button", { name: /Log out/ });
  await user.click(logoutButtons[logoutButtons.length - 1]);
  expect(await screen.findByPlaceholderText("doctor@clinic.in")).toBeInTheDocument();
});
