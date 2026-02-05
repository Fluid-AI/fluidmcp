import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Dashboard from "./pages/Dashboard";
import Status from "./pages/Status";
import ServerDetails from "./pages/ServerDetails";
import { ToolRunner } from "./pages/ToolRunner";
import Documentation from "./pages/Documentation";

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