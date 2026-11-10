import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { installFetchMock } from "../test/fetchMock";

test("registers a clinic owner and navigates to verify email", async () => {
  installFetchMock([
    { path: "/auth/me", status: 401 },
    {
      path: "/auth/register",
      status: 201,
      body: {
        id: 2,
        email: "new@example.com",
        full_name: "New Owner",
        role: "clinic_owner",
        clinic_id: 2,
        dev_verification_token: "dev-token-123",
      },
    },
  ]);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/register"]}>
      <App />
    </MemoryRouter>
  );
  await user.type(screen.getByPlaceholderText("Dr. Jane Doe"), "New Owner");
  await user.type(screen.getByPlaceholderText("My Clinic"), "Green Clinic");
  await user.type(screen.getByPlaceholderText("doctor@clinic.in"), "new@example.com");
  await user.type(screen.getByPlaceholderText("At least 8 characters"), "strong-pass-1");
  await user.type(screen.getByPlaceholderText("Re-enter password"), "strong-pass-1");
  await user.click(screen.getByRole("button", { name: /Create account/i }));
  expect(await screen.findByDisplayValue("dev-token-123")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Paste your verification token")).toBeInTheDocument();
});

test("shows client-side error for mismatched passwords", async () => {
  installFetchMock([{ path: "/auth/me", status: 401 }]);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/register"]}>
      <App />
    </MemoryRouter>
  );
  await user.type(screen.getByPlaceholderText("Dr. Jane Doe"), "New Owner");
  await user.type(screen.getByPlaceholderText("My Clinic"), "Green Clinic");
  await user.type(screen.getByPlaceholderText("doctor@clinic.in"), "new@example.com");
  await user.type(screen.getByPlaceholderText("At least 8 characters"), "strong-pass-1");
  await user.type(screen.getByPlaceholderText("Re-enter password"), "different-pass-9");
  await user.click(screen.getByRole("button", { name: /Create account/i }));
  expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
});
