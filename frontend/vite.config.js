import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_BASE_URL || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": { target },
        "/demo": { target },
      },
    },
    preview: {
      proxy: {
        "/api": { target },
        "/demo": { target },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.js",
      restoreMocks: true,
    },
  };
});
