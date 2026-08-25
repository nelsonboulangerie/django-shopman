import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const appAlias = {
  "~": fileURLToPath(new URL("./app", import.meta.url)),
  "@": fileURLToPath(new URL("./app", import.meta.url)),
};

export default defineConfig({
  test: {
    projects: [
      {
        resolve: { alias: appAlias, dedupe: ["vue"] },
        test: {
          name: "unit",
          environment: "node",
          globals: true,
          include: ["tests/**/*.test.ts"],
          exclude: ["tests/components/**", "tests/e2e/**", "node_modules/**"],
        },
      },
      {
        plugins: [vue()],
        resolve: { alias: appAlias },
        test: {
          name: "component",
          environment: "happy-dom",
          globals: true,
          include: ["tests/components/**/*.test.ts"],
        },
      },
    ],
  },
});
