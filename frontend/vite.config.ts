import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /api va al backend local: el navegador ve un solo origen y no hace falta CORS
// (SPEC-0001 RF-07). En la imagen, el mismo FastAPI sirve el build.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
