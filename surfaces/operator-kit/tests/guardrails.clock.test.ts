import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  formatClock,
  formatClockRange,
  formatClockSeconds,
  formatDateClock,
} from "../app/presentation/clock";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// Guardrail de HORA: a hora que alguém LÊ é "12h45" ("9h05", "9h"). O formato
// "12:45" não se escreve mais na tela. Decisão do dono em 16/11/2026, para a
// suíte inteira, operador e cliente; a regra está em
// `docs/reference/suite-vocabulary.md`, seção "Hora".
//
// Até essa data cada tela formatava a própria hora, e por isso conviviam
// "Aberto até 19h" e "aceite até 18:05". A trava não lê a frase: ela reprova o
// FORMATADOR antigo. Hora lida por gente passa por `app/presentation/clock.ts`,
// e mais nada formata hora.
//
// ## O que fica de fora, e como se declara
//
//   - **Formato de máquina**: o "HH:MM" que o servidor grava e o campo de hora
//     troca (`<input type="time">`, janela de campanha), ISO, e o formatador que
//     só CALCULA no fuso da loja. A linha (ou a linha de cima) leva
//     `// hora-ok: <motivo>`; marcador sem motivo não vale.
//   - **Duração não é hora**: "12 min", "1 h 20 min" seguem como estão.
//   - `generated/` é contrato gerado do servidor, e teste não é tela.
//
// ## As irmãs dela
//
// `shopman/backstage/tests/test_formato_de_hora.py` (servidor),
// `storefront-nuxt/tests/guardrails.clock.test.ts` (loja) e
// `status-nuxt/tests/guardrails.clock.test.ts` (status). A loja e o status não
// estendem o kit e buildam sozinhos: por isso têm o módulo GÊMEO e a trava deles.
//
// ⚠️ Ela lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Cada forma antiga de escrever a hora, com o nome que aparece na reprovação. */
const OLD_FORMS: ReadonlyArray<readonly [string, RegExp]> = [
  ["toLocaleTimeString", /toLocaleTimeString\(/],
  ["Intl com hora", /\bhour:\s*["'](?:2-digit|numeric)["']/],
  ["Intl com timeStyle", /\btimeStyle\b/],
  ["hora montada à mão com dois-pontos", /padStart\(2,\s*["']0["']\)\}:/],
  ["hora montada à mão com 'h'", /getHours\(\)\}h/],
];

const MARKER = /hora-ok:\s*\S/;

/** O formatador da casa: o único arquivo que monta a hora. */
const MAY_FORMAT = new Set(["operator-kit/app/presentation/clock.ts"]);

const SOURCE_EXT = [".ts", ".vue"];
const SKIP_DIRS = new Set(["node_modules", ".nuxt", ".output", "dist", "generated"]);

function sourceFiles(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry) || entry.startsWith(".output")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (SOURCE_EXT.some((extension) => full.endsWith(extension))) found.push(full);
  }
  return found;
}

/** O que o operador vê: `app/` e `server/` de cada superfície que usa o kit, e o kit. */
const SOURCES = [...OPERATOR_KIT_SURFACES, "operator-kit"]
  .flatMap((surface) => [
    ...sourceFiles(join(surfacesDir, surface, "app")),
    ...sourceFiles(join(surfacesDir, surface, "server")),
  ])
  .filter((file) => !MAY_FORMAT.has(relative(surfacesDir, file)));

function clockOffenders(text: string): string[] {
  const lines = text.split("\n");
  return lines.flatMap((line, index) => {
    if (MARKER.test(line) || MARKER.test(lines[index - 1] ?? "")) return [];
    const hit = OLD_FORMS.find(([, pattern]) => pattern.test(line));
    return hit ? [`${index + 1} (${hit[0]}): ${line.trim()}`] : [];
  });
}

describe("a hora na tela é 12h45", () => {
  it("nenhuma superfície de operador formata hora fora do formatador da casa", () => {
    const leaks = SOURCES.flatMap((file) =>
      clockOffenders(readFileSync(file, "utf8")).map(
        (offender) => `${relative(surfacesDir, file)}:${offender}`,
      ),
    );
    expect(
      leaks,
      'Use formatClock / formatDateClock de operator-kit/app/presentation/clock. Se é formato de máquina, declare na linha: "// hora-ok: <motivo>".',
    ).toEqual([]);
  });

  it("a trava reprova cada forma antiga", () => {
    const old = [
      'at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })',
      'new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" })',
      'new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" })',
      'const hhmm = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;',
      "const label = `${deadline.getHours()}h`;",
    ];
    for (const line of old) expect(clockOffenders(line), line).not.toEqual([]);
  });

  it("a trava conhece o que fica de fora", () => {
    expect(clockOffenders('  hour: "Hora",')).toEqual([]);
    expect(clockOffenders('  hour: "2-digit", // hora-ok: cálculo no fuso da loja, não exibição')).toEqual([]);
    expect(
      clockOffenders('  // hora-ok: o "HH:MM" que o servidor grava\n  const end = `${pad(h)}:${String(m).padStart(2, "0")}`;'),
    ).toEqual([]);
    // Marcador sem motivo não é exceção declarada.
    expect(clockOffenders('  hour: "2-digit", // hora-ok:')).not.toEqual([]);
  });

  it("a varredura lê as superfícies de verdade", () => {
    expect(SOURCES.length).toBeGreaterThan(500);
  });
});

describe("o formatador da casa", () => {
  const TZ = "America/Sao_Paulo";

  it("escreve a hora sem zero à esquerda, e a hora cheia sem minuto", () => {
    expect(formatClock("2026-11-16T15:45:00Z", TZ)).toBe("12h45");
    expect(formatClock("2026-11-16T12:05:00Z", TZ)).toBe("9h05");
    expect(formatClock("2026-11-16T12:00:00Z", TZ)).toBe("9h");
    expect(formatClock("2026-11-16T03:00:00Z", TZ)).toBe("0h");
    expect(formatClock(Date.parse("2026-11-16T15:45:00Z"), TZ)).toBe("12h45");
    expect(formatClock(new Date("2026-11-16T15:45:00Z"), TZ)).toBe("12h45");
  });

  it('lê o "HH:MM" dos contratos sem mexer no fuso', () => {
    expect(formatClock("07:00")).toBe("7h");
    expect(formatClock("18:05")).toBe("18h05");
    expect(formatClock("18:05:59")).toBe("18h05");
    expect(formatClock("9:30", TZ)).toBe("9h30");
  });

  it("o que não se lê fica vazio, nunca meia-noite", () => {
    for (const bad of [null, undefined, "", "lixo", "25:00", Number.NaN]) {
      expect(formatClock(bad as never, TZ)).toBe("");
    }
  });

  it("junta data e hora, e escreve o intervalo", () => {
    const at = "2026-11-16T15:45:00Z";
    expect(formatDateClock(at, { day: "2-digit", month: "2-digit" }, { timeZone: TZ })).toBe("16/11, 12h45");
    expect(
      formatDateClock(at, { day: "2-digit", month: "2-digit" }, { timeZone: TZ, joiner: " às " }),
    ).toBe("16/11 às 12h45");
    expect(formatDateClock("lixo", { day: "2-digit" })).toBe("");
    expect(formatClockRange("12:00", "14:30")).toBe("12h às 14h30");
    expect(formatClockRange("12:00", "")).toBe("12h");
  });

  it("com segundos, só onde o segundo é a informação", () => {
    expect(formatClockSeconds("2026-11-16T15:45:07Z", TZ)).toBe("12h45min07s");
    expect(formatClockSeconds("lixo", TZ)).toBe("");
  });
});

describe("o formatador é gêmeo na loja e no status", () => {
  const here = readFileSync(join(surfacesDir, "operator-kit/app/presentation/clock.ts"), "utf8");
  for (const twin of ["storefront-nuxt/app/utils/clock.ts", "status-nuxt/app/utils/clock.ts"]) {
    it(`é byte a byte igual a ${twin}`, () => {
      expect(readFileSync(join(surfacesDir, twin), "utf8"), `mude os três: ${twin}`).toBe(here);
    });
  }
});
