import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./tests/e2e", use: { viewport: { width: 1280, height: 860 } } });
