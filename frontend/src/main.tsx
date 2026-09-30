import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./styles.css";
import { Shell } from "./components/Shell";
import Home from "./pages/Home";
import Findings from "./pages/Findings";
import FindingDetail from "./pages/FindingDetail";
import Compare from "./pages/Compare";
import Claims from "./pages/Claims";
import CheckData from "./pages/CheckData";
import Report from "./pages/Report";
import Sources from "./pages/Sources";

function NotFound() {
  return (
    <div>
      <h1 className="text-3xl font-bold">Page not found</h1>
      <p className="text-ink-2">Use the navigation to return to the data health overview.</p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/findings" element={<Findings />} />
          <Route path="/findings/:id" element={<FindingDetail />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/claims" element={<Claims />} />
          <Route path="/check" element={<CheckData />} />
          <Route path="/report" element={<Report />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  </StrictMode>,
);
