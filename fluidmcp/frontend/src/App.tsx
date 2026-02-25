import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Dashboard from "./pages/Dashboard";
import Status from "./pages/Status";
import ServerDetails from "./pages/ServerDetails";
import { ToolRunner } from "./pages/ToolRunner";
import Documentation from "./pages/Documentation";
import { useAuth } from "./contexts/AuthContext";

function App() {
  const location = useLocation();
  const { checkAuth } = useAuth();

  // Handle return URL after Auth0 login
  useEffect(() => {
    const returnUrl = sessionStorage.getItem('auth_return_url');
    const pendingAction = sessionStorage.getItem('auth_pending_action');

    // Check if we just returned from OAuth and have a return URL
    if (returnUrl && window.location.pathname !== returnUrl) {
      // Clear the return URL
      sessionStorage.removeItem('auth_return_url');

      // Verify authentication
      checkAuth().then((isAuth) => {
        if (isAuth) {
          // Redirect back to the original page
          // The pending action will be replayed when that page loads
          window.location.href = returnUrl;
        }
      });
    }
    // If we're on the right page and have a pending action, replay it
    else if (pendingAction) {
      try {
        const action = JSON.parse(pendingAction);

        // Clear the pending action to prevent infinite loops
        sessionStorage.removeItem('auth_pending_action');

        // Verify authentication before replaying action
        checkAuth().then((isAuth) => {
          if (isAuth && action.action === 'start' && action.serverId) {
            // Trigger a custom event that the Dashboard can listen to
            window.dispatchEvent(new CustomEvent('replay-action', {
              detail: action
            }));
          }
        });
      } catch (error) {
        console.error('Failed to parse pending action:', error);
        sessionStorage.removeItem('auth_pending_action');
      }
    }
  }, [location, checkAuth]);

  return (
    <>
      <Toaster
        position="top-right"
        reverseOrder={false}
        gutter={8}
        toastOptions={{
          duration: 4000,
        }}
      />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/servers" element={<Dashboard />} />
        <Route path="/status" element={<Status />} />
        <Route path="/documentation" element={<Documentation />} />
        <Route path="/servers/:serverId" element={<ServerDetails />} />
        <Route path="/servers/:serverId/tools/:toolName" element={<ToolRunner />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </>
  );
}

export default App;