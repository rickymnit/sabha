import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AuthContextProps } from "react-oidc-context";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "./AuthProvider";
import { oidcSettings, readAuthConfig } from "./config";
import { ProtectedRoute, SignOutButton } from "./ProtectedRoute";
import { useAccessToken } from "./useAccessToken";

const oidc = vi.hoisted(() => ({
  auth: {} as Partial<AuthContextProps>,
  hasAuthParams: false,
}));

vi.mock("react-oidc-context", () => ({
  useAuth: () => oidc.auth,
  hasAuthParams: () => oidc.hasAuthParams,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function signedOut(): Partial<AuthContextProps> {
  return {
    isAuthenticated: false,
    isLoading: false,
    activeNavigator: undefined,
    error: undefined,
    user: undefined,
    signinRedirect: vi.fn(() => Promise.resolve()),
    signoutRedirect: vi.fn(() => Promise.resolve()),
  };
}

beforeEach(() => {
  oidc.auth = signedOut();
  oidc.hasAuthParams = false;
});

describe("readAuthConfig", () => {
  it("reads all three settings and drops the issuer's trailing slash", () => {
    expect(
      readAuthConfig({
        VITE_OIDC_AUTHORITY: "https://sabha-dev.example.auth0.com/",
        VITE_OIDC_CLIENT_ID: " spa-client ",
        VITE_OIDC_AUDIENCE: "https://api.example.com",
      }),
    ).toEqual({
      authority: "https://sabha-dev.example.auth0.com",
      clientId: "spa-client",
      audience: "https://api.example.com",
    });
  });

  it.each(["VITE_OIDC_AUTHORITY", "VITE_OIDC_CLIENT_ID", "VITE_OIDC_AUDIENCE"] as const)(
    "is null when %s is missing or blank",
    (name) => {
      const env = {
        VITE_OIDC_AUTHORITY: "https://issuer.example.com",
        VITE_OIDC_CLIENT_ID: "spa-client",
        VITE_OIDC_AUDIENCE: "https://api.example.com",
      };
      expect(readAuthConfig({ ...env, [name]: undefined })).toBeNull();
      expect(readAuthConfig({ ...env, [name]: "  " })).toBeNull();
    },
  );
});

describe("oidcSettings", () => {
  const settings = oidcSettings(
    { authority: "https://issuer.example.com", clientId: "spa-client", audience: "https://api.example.com" },
    "https://app.example.com",
  );

  it("uses the code flow back to this origin and asks for our API's audience", () => {
    expect(settings).toMatchObject({
      authority: "https://issuer.example.com",
      client_id: "spa-client",
      redirect_uri: "https://app.example.com/",
      post_logout_redirect_uri: "https://app.example.com/",
      extraQueryParams: { audience: "https://api.example.com" },
      automaticSilentRenew: true,
    });
  });

  it("asks for a refresh token so renewal needs no iframe", () => {
    expect(settings.scope?.split(" ")).toEqual(expect.arrayContaining(["openid", "offline_access"]));
  });

  it("clears the code and state from the address bar after the callback", () => {
    window.history.pushState({}, "", "/?code=abc&state=xyz");
    settings.onSigninCallback?.(undefined);
    expect(window.location.search).toBe("");
    expect(window.location.pathname).toBe("/");
  });
});

describe("AuthProvider", () => {
  it("explains what to set when sign-in is not configured", () => {
    render(
      <AuthProvider config={null}>
        <p>secret page</p>
      </AuthProvider>,
    );
    expect(screen.getByRole("heading", { name: "Sign-in is not set up" })).toBeInTheDocument();
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
  });
});

describe("ProtectedRoute", () => {
  it("shows the page to a signed-in person", () => {
    oidc.auth = { ...signedOut(), isAuthenticated: true };
    render(<ProtectedRoute>secret page</ProtectedRoute>);
    expect(screen.getByText("secret page")).toBeInTheDocument();
  });

  it("sends a signed-out person to sign in exactly once", () => {
    const { rerender } = render(<ProtectedRoute>secret page</ProtectedRoute>);
    rerender(<ProtectedRoute>secret page</ProtectedRoute>);
    expect(oidc.auth.signinRedirect).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Signing you in…");
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
  });

  it.each([
    ["the session is still loading", { isLoading: true }, false],
    ["a sign-in is already under way", { activeNavigator: "signinRedirect" as const }, false],
    ["the provider has just redirected back", {}, true],
  ])("does not redirect while %s", (_, state, callback) => {
    oidc.auth = { ...signedOut(), ...state };
    oidc.hasAuthParams = callback;
    render(<ProtectedRoute>secret page</ProtectedRoute>);
    expect(oidc.auth.signinRedirect).not.toHaveBeenCalled();
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
  });

  it("offers to sign in again after an error, without redirecting on its own", async () => {
    oidc.auth = { ...signedOut(), error: new Error("refresh failed") as AuthContextProps["error"] };
    render(<ProtectedRoute>secret page</ProtectedRoute>);
    expect(oidc.auth.signinRedirect).not.toHaveBeenCalled();
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sign in again" }));
    expect(oidc.auth.signinRedirect).toHaveBeenCalledTimes(1);
  });
});

describe("SignOutButton", () => {
  it("ends the session with the provider", async () => {
    oidc.auth = { ...signedOut(), isAuthenticated: true };
    render(<SignOutButton />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(oidc.auth.signoutRedirect).toHaveBeenCalledTimes(1);
  });
});

describe("useAccessToken", () => {
  function Token() {
    return <p>{useAccessToken() ?? "none"}</p>;
  }

  it("returns the access token when signed in, and nothing otherwise", () => {
    const { rerender } = render(<Token />);
    expect(screen.getByText("none")).toBeInTheDocument();

    oidc.auth = {
      ...signedOut(),
      isAuthenticated: true,
      user: { access_token: "tok-123" } as AuthContextProps["user"],
    };
    rerender(<Token />);
    expect(screen.getByText("tok-123")).toBeInTheDocument();
  });
});
