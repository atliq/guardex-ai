import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  base: "/",
  build: {
    outDir: path.resolve(__dirname, "../guardex/ui_assets"),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { "/v1": { target: "http://127.0.0.1:8001", changeOrigin: true } },
  },
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
});
