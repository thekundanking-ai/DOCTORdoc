import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Recorder from "./Recorder";
import { installMediaMocks } from "../test/mediaMock";

function renderRecorder(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  return render(<Recorder onSubmit={onSubmit} onBack={vi.fn()} />);
}

test("records, previews, and discards", async () => {
  installMediaMocks();
  const user = userEvent.setup();
  renderRecorder();

  await user.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(/Recording…/)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Stop" }));
  expect(await screen.findByTestId("preview-audio")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Discard" }));
  expect(screen.getByRole("button", { name: "Start recording" })).toBeInTheDocument();
});

test("submits the recorded blob", async () => {
  installMediaMocks();
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  renderRecorder(onSubmit);

  await user.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByText(/Recording…/);
  await user.click(screen.getByRole("button", { name: "Stop" }));
  await screen.findByTestId("preview-audio");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onSubmit.mock.calls[0][0]).toBeInstanceOf(Blob);
});

test("shows an error when microphone permission is denied", async () => {
  installMediaMocks({ denied: true });
  const user = userEvent.setup();
  renderRecorder();

  await user.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(/Permission denied/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start recording" })).toBeInTheDocument();
});
