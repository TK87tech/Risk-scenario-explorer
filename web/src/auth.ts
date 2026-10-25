// OIDC sign-in with Authorization Code + PKCE (oidc-client-ts handles the PKCE verifier and state).
// Roles are read for display only; the API enforces them on every request.
import { User, UserManager, WebStorageStateStore } from "oidc-client-ts";

export const userManager = new UserManager({
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8081/realms/grp-demo",
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "grp-web",
  redirect_uri: `${window.location.origin}/`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  response_type: "code",
  scope: "openid profile",
  // Session storage: tokens are cleared when the tab closes and are not shared across tabs.
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
});

/** Finish a sign-in redirect if the URL carries an authorization code; otherwise return the stored user. */
export async function initAuth(): Promise<User | null> {
  const params = new URLSearchParams(window.location.search);
  if (params.has("code") && params.has("state")) {
    const user = await userManager.signinRedirectCallback();
    window.history.replaceState({}, document.title, window.location.pathname);
    return user;
  }
  const user = await userManager.getUser();
  return user && !user.expired ? user : null;
}

export function rolesOf(user: User | null): string[] {
  if (!user) return [];
  try {
    const payload = JSON.parse(atob(user.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload?.realm_access?.roles ?? [];
  } catch {
    return [];
  }
}
