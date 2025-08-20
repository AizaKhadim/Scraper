import React from "react";
import { BrowserRouter as Router, Routes, Route, Link, useNavigate } from "react-router-dom";
import ScrapePage from "./ScrapePage";
import FirestoreResultsPage from "./FirestoreResultsPage";

function App() {
  return (
    <Router>
     
      <Routes>
        <Route path="/" element={<ScrapePage />} />
        <Route path="/results" element={<FirestoreResultsPage />} />
      </Routes>
    </Router>
  );
}

export default App;
