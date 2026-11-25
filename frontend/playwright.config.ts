import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: process.env.WEB_TEST_URL || "http://127.0.0.1:5173",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  timeout: 30000,
});
