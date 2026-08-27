import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"

// Dark mode is forced via class="dark" on <html> in index.html — no
// ThemeProvider, so nothing (hotkey or stored preference) can flip it.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
