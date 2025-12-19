import { Routes, Route } from "react-router-dom"
import Home from "./pages/Home"
import Airbnb from "./pages/Airbnb";
import './App.css'

function App() {
  return (
    <div style={{ padding: "24px" }}>
      
      <Routes>
        <Route path="/" element ={<Home />} />
        <Route path="/airbnb" element ={<Airbnb />} />
      </Routes>
    </div>
  );
}

export default App;