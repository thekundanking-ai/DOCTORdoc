import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { installFetchMock } from "./test/fetchMock";

test("redirects unauthenticated users to the login page", async () => {
  installFetchMock([{ path: "/auth/me", status: 401 }]);
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>
  );
  expect(await screen.findByRole("heading", { name: "DoctorDoc Sign in" })).toBeInTheDocument();
});
