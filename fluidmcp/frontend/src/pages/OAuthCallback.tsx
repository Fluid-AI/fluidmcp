import { useEffect } from "react";

/**
 * Fallback page at /oauth-callback.
 *
 * The actual OAuth popup is served by the backend's _oauth_popup_html which
 * calls window.close() directly. This React page only renders if someone
 * navigates to /oauth-callback directly in a non-popup context — it's a
 * graceful dead-end, nothing more.
 */
export default function OAuthCallback() {
  useEffect(() => {
    window.close();
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#09090b", color: "#fff", fontFamily: "sans-serif" }}>
      <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.9rem" }}>Authentication complete. Closing…</p>
    </div>
  );
}
