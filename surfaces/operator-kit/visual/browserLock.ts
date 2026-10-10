import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { readFileSync } from "node:fs";

import lock from "./browser-lock.json" with { type: "json" };

export interface BrowserLockResult {
  playwright: string;
  chromiumRevision: string;
  chromiumVersion: string;
}

export function readInstalledBrowserLock(cwd = process.cwd()): BrowserLockResult {
  const require = createRequire(join(cwd, "package.json"));
  const playwrightPackage = require("@playwright/test/package.json") as { version: string };
  const corePackagePath = require.resolve("playwright-core/package.json");
  const browsers = JSON.parse(readFileSync(join(dirname(corePackagePath), "browsers.json"), "utf8")) as {
    browsers: Array<{ name: string; revision: string; browserVersion: string }>;
  };
  const chromium = browsers.browsers.find((browser) => browser.name === "chromium");
  if (!chromium) throw new Error("playwright-core não declara Chromium");
  return {
    playwright: playwrightPackage.version,
    chromiumRevision: chromium.revision,
    chromiumVersion: chromium.browserVersion,
  };
}

export function assertPinnedOperatorBrowser(cwd = process.cwd()): BrowserLockResult {
  const installed = readInstalledBrowserLock(cwd);
  const expected = {
    playwright: lock.playwright,
    chromiumRevision: lock.chromium_revision,
    chromiumVersion: lock.chromium_version,
  };
  if (JSON.stringify(installed) !== JSON.stringify(expected)) {
    throw new Error(
      `Baseline recusada: Chromium incompatível. Esperado Playwright ${expected.playwright}, ` +
        `revisão ${expected.chromiumRevision} (${expected.chromiumVersion}); encontrado ` +
        `Playwright ${installed.playwright}, revisão ${installed.chromiumRevision} (${installed.chromiumVersion}).`,
    );
  }
  return installed;
}
