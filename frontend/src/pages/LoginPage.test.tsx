import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock, testUser } from "../test/fetchMock";

async function fillLogin(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText("Email"), email);
  await user.type(screen.getByPlaceholderText("Password"), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

test("logs in and navigates to the protected dashboard", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    { path: "/auth/login", status: 200, body: testUser() },
  ]);
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <App />
    </MemoryRouter>
  );
  await fillLogin("owner@example.com", "super-secret-1");
  expect(await screen.findByText(/Signed in as owner@example.com/)).toBeInTheDocument();
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
