import { readdirSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import { describe, expect, it } from "vitest";

const appRoot = new URL("../app/", import.meta.url);

function vueFiles(path = appRoot): URL[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, path);
    if (entry.isDirectory()) return vueFiles(child);
    return extname(entry.name) === ".vue" ? [child] : [];
  });
}

const sources = vueFiles().map((url) => ({
  file: url.pathname.split("/app/")[1],
  source: readFileSync(url, "utf8"),
}));

const sharedRuntimeFiles = [
  "ColumnPicker.vue",
  "FilterBar.vue",
  "OfflineBanner.vue",
  "OperatorAppRoot.vue",
  "OperatorAppSeal.vue",
  "OperatorConfirmDialog.vue",
  "OperatorIdentify.vue",
  "OperatorInbox.vue",
  "OperatorLiveStatus.vue",
  "OperatorLock.vue",
  "OperatorLogin.vue",
  "OperatorManagerAuth.vue",
  "OperatorMenuItems.vue",
  "OperatorOfficeShell.vue",
  "OperatorOrderContact.vue",
  "OperatorOrderDetail.vue",
  "OperatorOrderTimeline.vue",
  "OperatorPageHeader.vue",
  "OperatorPeriodPicker.vue",
  "OperatorPhoneMenu.vue",
  "OperatorPinChange.vue",
  "OperatorPwaInstallInvite.vue",
  "OperatorPwaRuntime.vue",
  "OperatorPwaUpdatePrompt.vue",
  "OperatorPushInvite.vue",
  "OperatorReasonDialog.vue",
  "OperatorSessionUnavailable.vue",
  "OperatorShortcutsHelp.vue",
  "OperatorStationSetup.vue",
  "OperatorSuiteSearch.vue",
  "OperatorSuiteShell.vue",
  "OperatorSonner.vue",
];

const sharedSources = sharedRuntimeFiles.map((file) => ({
  file: `operator-kit/${file}`,
  source: readFileSync(new URL(`../../operator-kit/app/components/${file}`, import.meta.url), "utf8"),
}));

const runtimeSources = [...sources, ...sharedSources];

function offenders(pattern: RegExp): string[] {
  return sources.filter(({ source }) => pattern.test(source)).map(({ file }) => file);
}

function runtimeOffenders(pattern: RegExp): string[] {
  return runtimeSources.filter(({ source }) => pattern.test(source)).map(({ file }) => file);
}

describe("Gestor canônico em Nuxt UI", () => {
  it("não mantém controles HTML ou wrappers visuais paralelos", () => {
    expect(runtimeOffenders(/<(?:button|input|select|textarea)\b/i)).toEqual([]);
    expect(runtimeOffenders(/<Ui[A-Z]|\b:ui=|\bui="/)).toEqual([]);
    expect(runtimeOffenders(/from ["']reka-ui["']/)).toEqual([]);
  });

  it("não recria overlays, menus, tabs ou alerts por ARIA manual", () => {
    expect(runtimeOffenders(/role="(?:alert|dialog|menu|menuitem|menuitemcheckbox|option|tab|tablist)"/)).toEqual([]);
  });

  it("não aplica skin local aos controles Nuxt UI", () => {
    const controls = "Button|Input|Textarea|Switch|Skeleton|Checkbox|Select|Badge|Alert|Tabs|Progress|RadioGroup|CheckboxGroup|Kbd|Chip|NavigationMenu|InputNumber";
    expect(offenders(new RegExp(`<Nuxt(?:${controls})\\b[^>]*\\b:?class=`, "s"))).toEqual([]);
    expect(offenders(new RegExp(`<Nuxt(?:${controls})\\b[^>]*\\b:?style=`, "s"))).toEqual([]);
  });

  it("usa o shell, o cabeçalho e as tabs canônicas no piloto", () => {
    const app = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");
    const board = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
    expect(app).toContain("<OperatorAppRoot>");
    expect(app).toContain("<OperatorSuiteShell");
    expect(app).not.toContain("<GestorNav");
    expect(board).toContain("<OperatorPageHeader");
    expect(board.match(/<NuxtTabs\b/g)?.length ?? 0).toBeGreaterThanOrEqual(5);
  });

  it("entrega cards e estados de feedback aos componentes Nuxt UI", () => {
    const card = readFileSync(new URL("../app/components/OrderCard.vue", import.meta.url), "utf8");
    expect(card).toMatch(/<NuxtCard\s+as="article"/);
    expect(offenders(/<article\b/)).toEqual([]);
    expect(offenders(/<style\b/)).toEqual([]);
  });
});
