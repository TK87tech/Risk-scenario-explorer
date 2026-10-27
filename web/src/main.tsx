import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Visitor counts (GoatCounter: no cookies, dashboard visible only to the account owner). Off unless configured.
const goatcounter = import.meta.env.VITE_GOATCOUNTER_URL;
if (goatcounter) {
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://gc.zgo.at/count.js";
  script.dataset.goatcounter = goatcounter;
  document.head.appendChild(script);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
