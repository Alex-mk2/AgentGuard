import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/inter/wght.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";

import { App } from "./App.tsx";
import "./estilos.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Falta el elemento #raiz en index.html");

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
