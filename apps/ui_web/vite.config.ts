import { defineConfig } from "vite";

const apiTarget = "http://127.0.0.1:8787";
const wsTarget = apiTarget.replace(/^http/, "ws");

export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/auth": apiTarget,
      "/admin": apiTarget,
      "/settings": apiTarget,
      "/uiport": apiTarget,
      "/ws": {
        target: wsTarget,
        ws: true,
      },
    },
  },
});
