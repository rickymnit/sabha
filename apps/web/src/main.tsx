import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import OverviewSpike from "./spike/OverviewSpike";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing from index.html");

createRoot(root).render(
  <StrictMode>
    <OverviewSpike />
  </StrictMode>,
);
