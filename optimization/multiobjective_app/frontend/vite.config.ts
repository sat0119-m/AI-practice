import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// npm run dev のときは /api を FastAPI (localhost:8000) に転送する
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
