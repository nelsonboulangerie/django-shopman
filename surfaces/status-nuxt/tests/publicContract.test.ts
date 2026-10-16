import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const worker = readFileSync(new URL("../functions/api/status.ts", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/assets/css/main.css", import.meta.url), "utf8");
const composable = readFileSync(new URL("../app/composables/usePublicStatus.ts", import.meta.url), "utf8");
const pwaRegistration = readFileSync(new URL("../app/plugins/pwaRegistration.client.ts", import.meta.url), "utf8");

describe("public projection contract", () => {
  it("publishes only named customer capabilities", () => {
    expect(worker).toContain('id: "online_store"');
    expect(worker).toContain('id: "service_operations"');
    expect(worker).not.toMatch(/token|certificate|database|redis|pool|migration|queue/i);
  });

  it("does not expose raw evidence or technical logs", () => {
    expect(page).not.toMatch(/evidence|stack trace|request id|database|redis|pool/i);
    expect(page).toContain("opera de forma independente do Shopman");
  });

  it("stays on the canonical Nuxt surface tokens", () => {
    expect(css).toContain("--color-background: var(--background)");
    expect(css).toContain("--color-muted-foreground: var(--muted-foreground)");
    expect(css).toContain("--color-success: var(--success)");
    expect(page).toContain("bg-background text-foreground");
    expect(css).toContain(".status-pill--operational { @apply bg-success/10 text-foreground; }");
    expect(css).not.toMatch(/--color-(canvas|surface|ink|wine|cream|brass)|--font-display/);
  });

  it("registers the offline shell without forcing an update mid-session", () => {
    expect(pwaRegistration).toContain("useRegisterSW({ immediate: true })");
    expect(pwaRegistration).not.toContain("updateServiceWorker(true)");
  });

  it("lets the edge share the short-lived probe result", () => {
    expect(composable).not.toContain("Date.now()");
    expect(worker).toContain("s-maxage=30");
  });
});
