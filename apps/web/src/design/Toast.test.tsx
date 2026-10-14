import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toast, ToastProvider } from "./Toast";
import { useToast, type ToastOptions } from "./toastContext";

function Trigger({ options }: { options: ToastOptions }) {
  const toast = useToast();
  return <button onClick={() => toast.show(options)}>Go</button>;
}

afterEach(() => vi.useRealTimers());

describe("Toast", () => {
  it("shows title, message and request id, and dismisses", () => {
    const onDismiss = vi.fn();
    render(<Toast tone="error" title="Upload failed" message="Try again." requestId="req_123" onDismiss={onDismiss} />);

    expect(screen.getByText("Upload failed")).toBeInTheDocument();
    expect(screen.getByText("req_123")).toHaveClass("select-all");
    expect(screen.getByText(/Request ID/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("enters with an animation only when motion is allowed", () => {
    const { container } = render(<Toast title="Saved" />);

    expect(container.firstElementChild).toHaveClass("motion-safe:animate-toast-in");
    expect(container.firstElementChild?.className).not.toMatch(/(^|\s)animate-/);
  });
});

describe("ToastProvider", () => {
  it("announces info politely and closes it after a while", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger options={{ title: "Saved" }} />
      </ToastProvider>,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");

    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(within(status).getByText("Saved")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(6000));
    expect(within(status).queryByText("Saved")).not.toBeInTheDocument();
  });

  it("announces errors as alerts with the request id and keeps them until dismissed", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger options={{ tone: "error", title: "Could not save", requestId: "req_abc" }} />
      </ToastProvider>,
    );
    const alert = screen.getByRole("alert");

    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(within(alert).getByText("Could not save")).toBeInTheDocument();
    expect(within(alert).getByText("req_abc")).toBeInTheDocument();
    expect(within(screen.getByRole("status")).queryByText("Could not save")).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(60000));
    expect(within(alert).getByText("Could not save")).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Dismiss notification" }));
    expect(within(alert).queryByText("Could not save")).not.toBeInTheDocument();
  });

  it("requires the provider", () => {
    // React and jsdom report the thrown render error; keep the expected noise out of the test output.
    const silence = (event: ErrorEvent) => event.preventDefault();
    window.addEventListener("error", silence);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      expect(() => render(<Trigger options={{ title: "x" }} />)).toThrow(/ToastProvider/);
    } finally {
      window.removeEventListener("error", silence);
      vi.restoreAllMocks();
    }
  });
});
