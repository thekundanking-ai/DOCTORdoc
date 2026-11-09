import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testUser } from "../test/fetchMock";

async function fillLogin(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText("doctor@clinic.in"), email);
  await user.type(screen.getByPlaceholderText("••••••••"), password);
  await user.click(screen.getByRole("button", { name: /Sign in/i }));
}

test("logs in and navigates to the dashboard", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    { path: "/auth/login", status: 200, body: testUser() },
    { path: "/patients", status: 200, body: { items: [], total: 0, page: 1, page_size: 5 } },
  ]);
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <App />
    </MemoryRouter>
  );
  await fillLogin("owner@example.com", "super-secret-1");
  expect(await screen.findByText("Add a patient")).toBeInTheDocument();
});

test("shows the generic error on failed login", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    { path: "/auth/login", status: 401, body: { detail: "Invalid credentials" } },
  ]);
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <App />
    </MemoryRouter>
  );
  await fillLogin("owner@example.com", "wrong-password");
  expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
});
