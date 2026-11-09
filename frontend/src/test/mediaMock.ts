import { vi } from "vitest";

export function audioBlob(mime = "audio/webm"): Blob {
  return new Blob([new Uint8Array([1, 2, 3])], { type: mime });
}

export class FakeMediaRecorder {
  static isTypeSupported(): boolean {
    return true;
  }

  mimeType = "audio/webm";
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: unknown, opts?: { mimeType?: string }) {
    this.mimeType = opts?.mimeType || "audio/webm";
  }

  start(): void {
    this.state = "recording";
  }

  stop(): void {
    this.state = "inactive";
    if (typeof this.ondataavailable === "function") {
      this.ondataavailable({ data: audioBlob(this.mimeType) });
    }
    if (typeof this.onstop === "function") {
      this.onstop();
    }
  }
}

export function installMediaMocks({ denied = false } = {}) {
  const tracks = [{ stop: vi.fn() }];
  const stream = { getTracks: () => tracks };
  const getUserMedia = denied
    ? vi.fn().mockRejectedValue(new Error("Permission denied"))
    : vi.fn().mockResolvedValue(stream);
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia },
    configurable: true,
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  return { getUserMedia, tracks };
}
