import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { UserManager, User, WebStorageStateStore, Log } from "oidc-client-ts";
import { config } from "../config";

Log.setLogger(console);
Log.setLevel(Log.WARN);

// sessionStorage, not localStorage: cleared when the tab closes, which
// bounds how long a stolen/leaked token stays usable via, e.g., an XSS
// payload that reads storage. This is oidc-client-ts's own persistence for
// the OIDC user record (access token + refresh token if issued); it's a
// standard, defensible trade-off for a browser SPA, not a full in-memory
// solution -- true in-memory-only storage would break session persistence
// across a page reload and silent token renewal.
const userManager = new UserManager({
  authority: config.oidcAuthority,
  client_id: config.oidcClientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: window.location.origin,
  response_type: "code",
  scope: "openid profile email",
  // Many IdPs (Auth0-style) require an explicit `audience` param to issue
  // an access token for a specific API rather than an ID-token-only
  // response. Harmless no-op on IdPs that ignore unknown params.
  extraQueryParams: config.oidcAudience ? { audience: config.oidcAudience } : {},
  automaticSilentRenew: true,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
});

type Principal = {
  userId: string;
  tenantId: string;
  roles: string[];
};

type AuthContextValue = {
  isLoading: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;
  principal: Principal | null;
  login: () => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function principalFromUser(user: User): Principal {
  const claims = user.profile as Record<string, unknown>;
  return {
    userId: (claims.sub as string) ?? "",
    // Custom claim namespace matches backend/auth/dependencies.py exactly
    // -- both sides must agree on this or tenant scoping silently breaks.
    tenantId: (claims["https://clinical-ai/tenant_id"] as string) ?? "",
    roles: (claims["https://clinical-ai/roles"] as string[]) ?? [],
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const onUserLoaded = (u: User) => setUser(u);
    const onUserUnloaded = () => setUser(null);
    const onSilentRenewError = (err: Error) => {
      // Silent renew failing usually means no refresh token was issued
      // (common for SPA clients per OAuth2 browser-app best practice) --
      // fall through to requiring a full interactive login rather than
      // retrying forever.
      console.warn("Silent token renewal failed, user will need to re-authenticate", err);
      setUser(null);
    };

    userManager.events.addUserLoaded(onUserLoaded);
    userManager.events.addUserUnloaded(onUserUnloaded);
    userManager.events.addSilentRenewError(onSilentRenewError);

    (async () => {
      try {
        if (window.location.pathname === "/auth/callback") {
          const u = await userManager.signinRedirectCallback();
          setUser(u);
          // Clean the auth code/state out of the URL bar before rendering
          // the app, rather than leaving them visible/bookmarkable.
          window.history.replaceState({}, document.title, "/");
        } else {
          const existing = await userManager.getUser();
          if (existing && !existing.expired) setUser(existing);
        }
      } catch (err) {
        console.error("Auth initialization failed", err);
      } finally {
        setIsLoading(false);
      }
    })();

    return () => {
      userManager.events.removeUserLoaded(onUserLoaded);
      userManager.events.removeUserUnloaded(onUserUnloaded);
      userManager.events.removeSilentRenewError(onSilentRenewError);
    };
  }, []);

  const login = useCallback(() => {
    userManager.signinRedirect();
  }, []);

  const logout = useCallback(() => {
    userManager.signoutRedirect();
  }, []);

  const value: AuthContextValue = {
    isLoading,
    isAuthenticated: !!user && !user.expired,
    accessToken: user?.access_token ?? null,
    principal: user ? principalFromUser(user) : null,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
