import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Dashboard from "./pages/Dashboard";
import Status from "./pages/Status";
import ServerDetails from "./pages/ServerDetails";
import { ToolRunner } from "./pages/ToolRunner";
import Documentation from "./pages/Documentation";
import LLMModels from "./pages/LLMModels";
import LLMModelDetails from "./pages/LLMModelDetails";
import LLMPlayground from "./pages/LLMPlayground";
import ManageServers from "./pages/ManageServers";

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
        <Route path="/servers/manage" element={<ManageServers />} />
        <Route path="/documentation" element={<Documentation />} />
        <Route path="/servers/:serverId" element={<ServerDetails />} />
        <Route path="/servers/:serverId/tools/:toolName" element={<ToolRunner />} />
        <Route path="/llm/models" element={<LLMModels />} />
        <Route path="/llm/models/:modelId" element={<LLMModelDetails />} />
        <Route path="/llm/playground" element={<LLMPlayground />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </>
  );
}

export default App;