import { Routes, Route } from "react-router-dom"
import Home from "./pages/Home"
import Airbnb from "./pages/Airbnb";
import './App.css'

function App() {
  return (
    <div style={{ padding: "24px" }}>
      {/* Application routes */}
      <Routes>
        {/* Home page showing available MCP tools */}
        <Route path="/" element ={<Home />} />

        {/* Airbnb MCP tool UI */}
        <Route path="/airbnb" element ={<Airbnb />} />
      </Routes>
    </div>
  );
}

export default App;