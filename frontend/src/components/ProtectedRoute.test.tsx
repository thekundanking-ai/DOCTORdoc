import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testUser } from "../test/fetchMock";

test("allows access to protected route when authenticated", async () => {
  installFetchMock([{ path: "/auth/me", status: 200, body: testUser() }]);
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>
  );
  expect(await screen.findByText(/Signed in as owner@example.com/)).toBeInTheDocument();
});

test("logout clears session and returns to login", async () => {
  installFetchMock([
    { path: "/auth/me", status: 200, body: testUser() },
    { path: "/auth/logout", status: 200, body: { ok: true } },
  ]);
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>
  );
  await screen.findByText(/Signed in as owner@example.com/);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("heading", { name: "DoctorDoc Sign in" })).toBeInTheDocument();
});
