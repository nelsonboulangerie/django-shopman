import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import lock from "../visual/browser-lock.json";

describe("lock do Chromium visual", () => {
  it("acompanha a versão travada nos consumers representativos", () => {
    for (const app of ["marketing-nuxt", "pos-nuxt", "production-nuxt"]) {
      const packageLock = JSON.parse(readFileSync(new URL(`../../${app}/package-lock.json`, import.meta.url), "utf8"));
      expect(packageLock.packages["node_modules/@playwright/test"].version, app).toBe(lock.playwright);
      expect(packageLock.packages["node_modules/playwright-core"].version, app).toBe(lock.playwright);
    }
    expect(lock.chromium_revision).toBe("1243");
  });
});
