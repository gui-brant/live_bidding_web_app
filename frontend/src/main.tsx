import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./app/App";
import "./styles.css";

const storedTheme = (() => {
  try {
    return localStorage.getItem("theme") || "light";
  } catch {
    return "light";
  }
})();

document.documentElement.dataset.theme = storedTheme;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
