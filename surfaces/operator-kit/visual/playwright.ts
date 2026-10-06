import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { Page, PlaywrightTestConfig, TestInfo } from "@playwright/test";

import { selectedOperatorViewports, type OperatorVisualViewport } from "./matrix";
import { scanOperatorGeometry, type OperatorGeometryFinding } from "./scanner";

const visualRoot = dirname(fileURLToPath(import.meta.url));

export interface OperatorVisualConfigOptions {
  app: string;
  testDir: string;
  outputDir?: string;
  snapshotPathTemplate?: string;
  webServer?: PlaywrightTestConfig["webServer"];
  use?: PlaywrightTestConfig["use"];
  matrix?: boolean;
}

export interface OperatorEvidenceIdentity {
  app: string;
  surface: string;
  route: string;
  scenario: string;
  state: string;
  theme?: "light" | "dark";
  viewport: OperatorVisualViewport;
}

export function defineOperatorVisualConfig(options: OperatorVisualConfigOptions): PlaywrightTestConfig {
  const matrix = options.matrix === false ? null : selectedOperatorViewports();
  return {
    testDir: options.testDir,
    testMatch: "**/*.spec.ts",
    outputDir: options.outputDir ?? "./test-results/operator-visual",
    snapshotPathTemplate: options.snapshotPathTemplate ?? "{testDir}/baselines/{arg}{ext}",
    fullyParallel: false,
    forbidOnly: true,
    retries: 0,
    workers: 1,
    // O primeiro navegador de cada servidor de dev paga a compilação lazy do
    // bundle; 60s de teste / 10s de asserção reprovavam por frio, não por bug.
    timeout: 90_000,
    globalSetup: join(visualRoot, "globalSetup.ts"),
    reporter: [["list"], [join(visualRoot, "reporter.ts")]],
    expect: {
      timeout: 45_000,
      toHaveScreenshot: { animations: "disabled", caret: "hide", maxDiffPixelRatio: 0.001, threshold: 0.2 },
    },
    ...(options.webServer ? { webServer: options.webServer } : {}),
    ...(matrix
      ? {
          projects: matrix.map((viewport) => ({
            name: viewport.id,
            metadata: { operatorViewport: viewport, operatorApp: options.app },
            use: {
              viewport: {
                width: Math.round(viewport.width / (viewport.zoom ?? 1)),
                height: Math.round(viewport.height / (viewport.zoom ?? 1)),
              },
              hasTouch: viewport.touch,
              isMobile: viewport.profile === "mobile-touch",
              deviceScaleFactor: viewport.zoom ?? 1,
            },
          })),
        }
      : {}),
    use: {
      browserName: "chromium",
      headless: true,
      colorScheme: "light",
      locale: "pt-BR",
      reducedMotion: "reduce",
      serviceWorkers: "block",
      timezoneId: "America/Sao_Paulo",
      trace: "retain-on-failure",
      ...options.use,
    },
  };
}

export function operatorScenarioSelected(identity: Pick<OperatorEvidenceIdentity, "app" | "route" | "scenario">): boolean {
  const selections = {
    app: process.env.OPERATOR_VISUAL_APP,
    route: process.env.OPERATOR_VISUAL_ROUTE,
    scenario: process.env.OPERATOR_VISUAL_SCENARIO,
  };
  return Object.entries(selections).every(([key, value]) => !value || identity[key as keyof typeof identity] === value);
}

export async function captureOperatorEvidence(
  page: Page,
  testInfo: TestInfo,
  identity: OperatorEvidenceIdentity,
  options: { fullPage?: boolean; scan?: boolean; allowedFindings?: readonly OperatorGeometryFinding["kind"][] } = {},
) {
  await page.evaluate(() => document.fonts.ready);
  const findings = options.scan === false ? [] : await scanOperatorGeometry(page, { touch: identity.viewport.touch });
  const allowed = new Set(options.allowedFindings ?? []);
  const blocking = findings.filter((finding) => !allowed.has(finding.kind));
  const slug = [identity.app, identity.surface, identity.scenario, identity.state, identity.viewport.id, identity.theme ?? "light"].join("__");
  const screenshot = testInfo.outputPath(`${slug}.png`);
  await page.screenshot({ path: screenshot, fullPage: options.fullPage ?? true, animations: "disabled", caret: "hide" });
  testInfo.annotations.push({ type: "operator-evidence", description: JSON.stringify({ ...identity, findings }) });
  await testInfo.attach(`operator-evidence:${slug}`, { path: screenshot, contentType: "image/png" });
  if (blocking.length) {
    throw new Error(blocking.map((finding) => `${finding.kind} ${finding.selector}: ${finding.message}`).join("\n"));
  }
  return { screenshot, findings };
}
