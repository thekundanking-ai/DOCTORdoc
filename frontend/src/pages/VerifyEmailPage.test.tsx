import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock } from "../test/fetchMock";

const devEntry = {
  pathname: "/verify-email",
  state: { email: "new@example.com", devToken: "dev-token-123" },
};

test("dev mode: verifies with dev token and shows sign-in button", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    { path: "/auth/verify-email", method: "POST", status: 200, body: { ok: true } },
  ]);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[devEntry]}>
      <App />
    </MemoryRouter>
  );
  await user.click(await screen.findByRole("button", { name: /Verify email/i }));
  expect(await screen.findByText(/Email verified/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Sign In/i }));
  expect(await screen.findByText("Need an account?")).toBeInTheDocument();
});

test("dev mode: shows friendly message for invalid token", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    {
      path: "/auth/verify-email",
      method: "POST",
      status: 400,
      body: { detail: "Invalid or expired verification token" },
    },
  ]);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[devEntry]}>
      <App />
    </MemoryRouter>
  );
  await user.click(await screen.findByRole("button", { name: /Verify email/i }));
  expect(await screen.findByText(/Invalid verification token/i)).toBeInTheDocument();
});

test("dev mode: shows friendly message for expired token", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    {
      path: "/auth/verify-email",
      method: "POST",
      status: 400,
      body: { detail: "Verification token has expired" },
    },
  ]);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[devEntry]}>
      <App />
    </MemoryRouter>
  );
  await user.click(await screen.findByRole("button", { name: /Verify email/i }));
  expect(await screen.findByText(/has expired/i)).toBeInTheDocument();
});

test("prod mode: shows check-email message with no token exposed", async () => {
  installFetchMock([{ path: "/auth/me", status: 401 }]);
  render(
    <MemoryRouter initialEntries={["/verify-email"]}>
      <App />
    </MemoryRouter>
  );
  expect(await screen.findByText("Check your email and use the verification link.")).toBeInTheDocument();
  expect(screen.queryByPlaceholderText("Paste your verification token")).not.toBeInTheDocument();
  expect(screen.queryByText("dev-token-123")).not.toBeInTheDocument();
});
