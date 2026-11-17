import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { formatClock, formatDateClock } from "../app/utils/clock";

// Guardrail de HORA, a metade da página de status: a hora que alguém LÊ é
// "12h45" ("9h05", "9h"). Decisão do dono em 16/11/2026, para a suíte inteira;
// a regra está em `docs/reference/suite-vocabulary.md`, seção "Hora".
//
// O status é independente (não estende o operator-kit e builda sozinho), então
// o formatador é um módulo GÊMEO do de `operator-kit/app/presentation/clock.ts`,
// byte a byte, e a trava do kit não varre esta pasta. Esta varre. Formato de
// máquina se declara na linha (ou na de cima) com `// hora-ok: <motivo>`.

const root = fileURLToPath(new URL("..", import.meta.url));
const here = join(root, "app/utils/clock.ts");
const twin = fileURLToPath(new URL("../../operator-kit/app/presentation/clock.ts", import.meta.url));

const OLD_FORMS: ReadonlyArray<readonly [string, RegExp]> = [
  ["toLocaleTimeString", /toLocaleTimeString\(/],
  ["Intl com hora", /\bhour:\s*["'](?:2-digit|numeric)["']/],
  ["Intl com timeStyle", /\btimeStyle\b/],
  ["hora montada à mão com dois-pontos", /padStart\(2,\s*["']0["']\)\}:/],
  ["hora montada à mão com 'h'", /getHours\(\)\}h/],
];
const MARKER = /hora-ok:\s*\S/;
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist"]);

function sourceFiles(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".ts") || full.endsWith(".vue")) found.push(full);
  }
  return found;
}

const SOURCES = [...sourceFiles(join(root, "app")), ...sourceFiles(join(root, "functions"))].filter(
  (file) => file !== here,
);

function clockOffenders(text: string): string[] {
  const lines = text.split("\n");
  return lines.flatMap((line, index) => {
    if (MARKER.test(line) || MARKER.test(lines[index - 1] ?? "")) return [];
    const hit = OLD_FORMS.find(([, pattern]) => pattern.test(line));
    return hit ? [`${index + 1} (${hit[0]}): ${line.trim()}`] : [];
  });
}

describe("a hora na página de status é 12h45", () => {
  it("nada formata hora fora do formatador da casa", () => {
    const leaks = SOURCES.flatMap((file) =>
      clockOffenders(readFileSync(file, "utf8")).map((offender) => `${relative(root, file)}:${offender}`),
    );
    expect(leaks, 'Use formatClock / formatDateClock de ~/utils/clock. Formato de máquina: "// hora-ok: <motivo>".').toEqual([]);
  });

  it("a trava reprova a forma antiga, e a varredura lê arquivos de verdade", () => {
    expect(clockOffenders('new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" })')).not.toEqual([]);
    expect(SOURCES.length).toBeGreaterThan(3);
  });

  it("o formatador é byte a byte igual ao do operator-kit", () => {
    expect(readFileSync(here, "utf8"), `mude os gêmeos: ${twin}`).toBe(readFileSync(twin, "utf8"));
  });

  it("escreve a hora como a casa escreve", () => {
    const TZ = "America/Sao_Paulo";
    expect(formatClock("2026-11-16T15:45:00Z", TZ)).toBe("12h45");
    expect(formatDateClock("2026-11-16T15:45:00Z", { dateStyle: "medium" }, { timeZone: TZ })).toBe(
      "16 de nov. de 2026, 12h45",
    );
  });
});
