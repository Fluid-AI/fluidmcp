import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Dashboard from "./pages/Dashboard";
import ServerDetails from "./pages/ServerDetails";
import { ToolRunner } from "./pages/ToolRunner";
import ComponentShowcase from "./pages/ComponentShowcase";

function App() {
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
        <Route path="/showcase" element={<ComponentShowcase />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/servers/:serverId" element={<ServerDetails />} />
        <Route path="/servers/:serverId/tools/:toolName" element={<ToolRunner />} />
        <Route path="*" element={<Navigate to="/dashboard" />} />
      </Routes>
    </>
  );
}

export default App;