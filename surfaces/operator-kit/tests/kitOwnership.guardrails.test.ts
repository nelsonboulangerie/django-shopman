import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES as OPERATOR_APPS } from "./support/surfaceRegistry";

// Guardrail de PROPRIEDADE: o que o kit já possui não volta a nascer copiado no app.
//
// Motivo medido: `apiPath` existia em SETE cópias com TRÊS nomes (`apiPath`,
// `hubApiPath`, `posApiPath`), `operatorSessionOnError` em SEIS, a casca do BFF
// `/api/v1/**` nos OITO, e as quatro primitivas de barra em duas — e a cópia mais
// nova tinha trocado o token de alvo de toque por literal, derrubando o chip para
// 36 px. Cópia byte a byte não dói no dia em que é feita; dói no dia em que UMA
// delas muda. Este arquivo é o teste de varredura que cobra o gêmeo que falta:
// quem precisar da peça importa do kit, e quem precisar de comportamento DIFERENTE
// dá um nome próprio (é o que o Marketing faz com `marketingSessionOnError`).
//
// Storefront fica FORA: não estende esta layer (superfície de cliente, proxy, CSRF
// e harness próprios).

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");


/** Declarações que pertencem ao kit e não podem reaparecer no app — inclusive com
 * outro nome, que foi exatamente como as sete cópias de `apiPath` se esconderam.
 * O gatilho é o `export` (a peça sendo REDECLARADA), não o `const apiPath = ...`
 * com que cada chamador amarra o retorno de `useApiPath()`. */
const KIT_OWNED_DECLARATIONS = [
  /\bexport\s+(?:function|const)\s+\w*[aA]piPath\b/,
  /\bexport\s+(?:function|const)\s+operatorSessionOnError\b/,
] as const;

/** Componentes de barra que agora vivem no kit (nome global `Ui<Nome>`). */
const KIT_OWNED_TOOLBAR_PRIMITIVES = ["FilterChip", "IconButton", "SearchInput"] as const;

/**
 * Primitivos de ESCOLHA, que passaram a viver no kit. Antes deles todo checkbox e
 * todo rádio das nove superfícies era o controle nativo do browser com uma tinta
 * do Tailwind por cima, e o select com busca existia UMA vez, escondido no
 * Compras como `MaterialPicker` — que foi promovido a `UiSelect`. Se um app
 * recriar a peça, a busca que ignora acento, o `mixed` do indeterminado e a
 * armadilha do `<label>` voltam a existir em duas versões, e uma delas erra.
 *
 * `Switch` entrou por último e pela porta oposta: ele EXISTIA (o do PDV, montado
 * por 7 telas), e mais três telas tinham reescrito o mesmo trilho à mão — em três
 * tamanhos, com duas cores de trilho desligado, e a do PDV num alvo de toque de
 * 24 px. Não é hipótese de deriva: é a deriva medida.
 *
 * `ToggleChip` fechou o vazio que a própria conversão dos outros tinha registrado em
 * comentário: escolha múltipla desenhada como pílula, onde o quadrado com rótulo ao
 * lado seria a peça parecida no lugar da certa. Antes dele havia 50 `aria-pressed`
 * escritos à mão nas superfícies de operador, mais as pílulas de plataforma do
 * Marketing embrulhando um `<input class="sr-only">` num `<label>` pintado — três
 * desenhos para o mesmo gesto.
 */
const KIT_OWNED_CHOICE_PRIMITIVES = [
  "Checkbox",
  "CheckboxGroup",
  "Radio",
  "RadioGroup",
  "Select",
  "Stepper",
  "Switch",
  "Tabs",
  "ToggleChip",
] as const;

/** Campos temporais preservam strings das APIs, mas sua anatomia é única. */
const KIT_OWNED_TEMPORAL_PRIMITIVES = [
  "DateField",
  "DateRangeField",
  "DateTimeField",
  "TimeField",
  "TimeRangeField",
] as const;

/** Feedback visual de carregamento permanece no Nuxt UI em toda a suíte. */
const KIT_OWNED_FEEDBACK_PRIMITIVES = ["Skeleton"] as const;

/** Nomes próprios que a promoção do `UiSelect` aposentou. */
const RETIRED_COMPONENTS = ["MaterialPicker"] as const;

/**
 * Data, hora e período são `UiDateField`, `UiDateRangeField`, `UiTimeField`,
 * `UiTimeRangeField` e `UiDateTimeField` (decisão do dono), nunca o seletor nativo.
 *
 * A trava antiga casava só `<input type="date">` e só nos apps, e a pilha do Gestor
 * passou por baixo dela duas vezes: trocou o `UiDateField` do `OperatorPeriodPicker`
 * por `<NuxtInput type="date">` (outro nome de tag) DENTRO do kit (pasta que a
 * trava não varria), e o período dos 5 apps que o montam virou nativo sem nenhum
 * teste reprovar. Agora casa as quatro portas para o nativo (`input`, `NuxtInput`,
 * `UInput`, `UiInput`), o `type` literal e o `:type` dinâmico que pode dar data,
 * e varre o kit também.
 */
const TEMPORAL_TYPE = "(?:date|time|datetime-local|month|week)";
const TEXT_INPUT_TAG =
  /<(?:input|NuxtInput|UInput|UiInput)\b(?:[^>"']|"[^"]*"|'[^']*')*>/g;
const NATIVE_TEMPORAL_TYPE = new RegExp(
  `\\s(?:type=["']${TEMPORAL_TYPE}["']|(?::|v-bind:)type="[^"]*'${TEMPORAL_TYPE}'[^"]*")`,
);

/**
 * Débito conhecido, com dono e prazo, que a trava nova encontrou no primeiro dia.
 * É teto: a lista só encolhe. Um arquivo daqui que deixar de usar o nativo
 * reprova o teste até sair da lista, para a exceção não sobreviver ao motivo.
 */
const KNOWN_NATIVE_TEMPORAL: Readonly<Record<string, string>> = {
  "orders-nuxt/app/components/ChannelPeriodCalendar.vue":
    "Gestor: a pilha canônica trocou por NuxtInput type=date/time (de/até com hora). " +
    "O Gestor tem dono; a troca por UiDateTimeField é dele, na migração do app (onda 0, PR 0.3).",
};

function nativeTemporalOffenders(dir: string): string[] {
  return sourceFiles(dir)
    .filter((file) =>
      [...sourceWithoutComments(file).matchAll(TEXT_INPUT_TAG)].some(([tag]) =>
        NATIVE_TEMPORAL_TYPE.test(tag),
      ),
    )
    .map((file) => file.slice(surfacesDir.length + 1));
}

function sourceFiles(dir: string, found: string[] = []): string[] {
  if (!existsSync(dir)) return found;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".ts") || full.endsWith(".vue")) found.push(full);
  }
  return found;
}

function sourceWithoutComments(file: string): string {
  const source = readFileSync(file, "utf8");
  let clean = "";
  let index = 0;

  while (index < source.length) {
    const next = source.slice(index);
    if (next.startsWith("/*")) {
      const end = source.indexOf("*/", index + 2);
      index = end === -1 ? source.length : end + 2;
      continue;
    }
    if (next.startsWith("//")) {
      const end = source.indexOf("\n", index + 2);
      if (end === -1) break;
      clean += "\n";
      index = end + 1;
      continue;
    }
    if (next.startsWith("<!--")) {
      const end = source.indexOf("-->", index + 4);
      index = end === -1 ? source.length : end + 3;
      continue;
    }

    clean += source[index];
    index += 1;
  }

  return clean;
}

describe("operator-kit: o que é do kit não renasce copiado no app", () => {
  for (const app of OPERATOR_APPS) {
    it(`${app} não redeclara apiPath nem operatorSessionOnError`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        const source = readFileSync(file, "utf8");
        for (const pattern of KIT_OWNED_DECLARATIONS) {
          if (pattern.test(source)) {
            offenders.push(`${file.slice(surfacesDir.length + 1)} → ${pattern.source}`);
          }
        }
      }
      expect(
        offenders,
        `Peça do kit redeclarada no app (importe do operator-kit; se o comportamento ` +
          `for DIFERENTE, dê um nome próprio como o marketingSessionOnError):\n  ` +
          offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não tem cópia própria das primitivas de barra`, () => {
      const offenders = KIT_OWNED_TOOLBAR_PRIMITIVES.filter((name) =>
        existsSync(resolve(surfacesDir, app, "app/components/Ui", `${name}.vue`)),
      );
      expect(
        offenders,
        `Primitiva de barra copiada no app: ${offenders.join(", ")}. ` +
          `A canônica é <Ui${offenders[0] ?? "…"}> do operator-kit.`,
      ).toEqual([]);
    });

    it(`${app} não tem cópia própria dos primitivos de escolha`, () => {
      const offenders = KIT_OWNED_CHOICE_PRIMITIVES.filter(
        (name) =>
          existsSync(resolve(surfacesDir, app, "app/components/Ui", `${name}.vue`)) ||
          existsSync(resolve(surfacesDir, app, "app/components/Ui", name, `${name}.vue`)),
      );
      expect(
        offenders,
        `Primitivo de escolha copiado no app: ${offenders.join(", ")}. ` +
          `O canônico é <Ui${offenders[0] ?? "…"}> do operator-kit.`,
      ).toEqual([]);
    });

    it(`${app} não tem cópia própria dos campos de data e hora`, () => {
      const offenders = KIT_OWNED_TEMPORAL_PRIMITIVES.filter((name) =>
        existsSync(resolve(surfacesDir, app, "app/components", `Ui${name}.vue`)),
      );
      expect(
        offenders,
        `Campo temporal copiado no app: ${offenders.join(", ")}. ` +
          `O canônico é <Ui${offenders[0] ?? "…"}> do operator-kit.`,
      ).toEqual([]);
    });

    it(`${app} não tem cópia própria dos primitivos de feedback`, () => {
      const offenders = KIT_OWNED_FEEDBACK_PRIMITIVES.filter((name) =>
        existsSync(resolve(surfacesDir, app, "app/components", `Ui${name}.vue`)),
      );
      expect(
        offenders,
        `Primitivo de feedback copiado no app: ${offenders.join(", ")}. ` +
          `O canônico é <Ui${offenders[0] ?? "…"}> do operator-kit.`,
      ).toEqual([]);
    });

    it(`${app} não reconstrói Skeleton com classes soltas`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        const source = sourceWithoutComments(file);
        if (/class=["'][^"']*animate-pulse[^"']*bg-muted|class=["'][^"']*bg-muted[^"']*animate-pulse/.test(source)) {
          offenders.push(file.slice(surfacesDir.length + 1));
        }
      }
      expect(
        offenders,
        `Skeleton artesanal encontrado (use <UiSkeleton> do operator-kit):\n  ` + offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não reescreve o interruptor à mão`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        // `role="switch"` fora do kit é o trilho reescrito: foi assim que o
        // Marketing e o Gestor de Pedidos ficaram com três tamanhos do MESMO
        // controle, sem nenhum arquivo em comum para corrigir de uma vez.
        if (/role="switch"/.test(readFileSync(file, "utf8"))) {
          offenders.push(file.slice(surfacesDir.length + 1));
        }
      }
      expect(
        offenders,
        `Interruptor escrito à mão (use <UiSwitch> do operator-kit):\n  ` + offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não reescreve abas compostas à mão`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        const source = sourceWithoutComments(file);
        if (/\brole=["']tablist["']/.test(source)) {
          offenders.push(file.slice(surfacesDir.length + 1));
        }
      }
      expect(
        offenders,
        `Abas escritas à mão (use <UiTabs>, <UiTabsList> e <UiTabsTrigger>):\n  ` + offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não devolve checkbox ou rádio ao desenho nativo do sistema`, () => {
      const offenders: string[] = [];
      for (const file of sourceFiles(resolve(surfacesDir, app, "app"))) {
        const source = sourceWithoutComments(file);
        if (/<input(?=[^>]*\btype=["'](?:checkbox|radio)["'])[^>]*>/i.test(source)) {
          offenders.push(file.slice(surfacesDir.length + 1));
        }
      }
      expect(
        offenders,
        `Controle binário nativo encontrado (use <UiCheckbox> ou <UiRadioGroup>):\n  ` + offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não devolve data ou hora ao seletor nativo do sistema`, () => {
      const found = nativeTemporalOffenders(resolve(surfacesDir, app, "app"));
      const offenders = found.filter((file) => !(file in KNOWN_NATIVE_TEMPORAL));
      const cured = Object.keys(KNOWN_NATIVE_TEMPORAL).filter(
        (file) => file.startsWith(`${app}/`) && !found.includes(file),
      );
      expect(
        cured,
        `Exceção sem motivo: o arquivo já não usa o nativo; tire-o de KNOWN_NATIVE_TEMPORAL:\n  ` +
          cured.join("\n  "),
      ).toEqual([]);
      expect(
        offenders,
        `Campo temporal nativo encontrado (use <UiDateField>, <UiTimeField> ou <UiDateTimeField>):\n  ` +
          offenders.join("\n  "),
      ).toEqual([]);
    });

    it(`${app} não guarda o seletor com busca que virou UiSelect`, () => {
      const offenders = RETIRED_COMPONENTS.filter((name) =>
        existsSync(resolve(surfacesDir, app, "app/components", `${name}.vue`)),
      );
      expect(
        offenders,
        `${offenders.join(", ")} foi promovido ao kit como <UiSelect>; ` +
          `duas implementações vivas é como a busca do balcão perde uma garantia em silêncio.`,
      ).toEqual([]);
    });

    it(`${app} usa a rota /api/v1/** do kit, sem casca própria`, () => {
      expect(
        existsSync(resolve(surfacesDir, app, "server/api/v1/[...path].ts")),
        `${app} recriou a casca do BFF; o handler único vive em ` +
          `operator-kit/server/api/v1/[...path].ts e chega por extends.`,
      ).toBe(false);
    });
  }

  it("o kit não devolve data ou hora ao seletor nativo do sistema", () => {
    // O kit é o dono dos campos de data: se ele usa o nativo, os nove herdam.
    const offenders = nativeTemporalOffenders(resolve(surfacesDir, "operator-kit/app"));
    expect(
      offenders,
      `Campo temporal nativo no kit (use <UiDateField>, <UiDateRangeField>, <UiTimeField> ou <UiDateTimeField>):\n  ` +
        offenders.join("\n  "),
    ).toEqual([]);
  });

  it("a trava de campo temporal nativo pega as quatro portas e o :type dinâmico", () => {
    const catches = (tag: string) =>
      [...tag.matchAll(TEXT_INPUT_TAG)].some(([match]) => NATIVE_TEMPORAL_TYPE.test(match));
    expect(catches('<input type="date">')).toBe(true);
    expect(catches('<NuxtInput v-model="from" type="date" :min="min" />')).toBe(true);
    expect(catches('<UInput type="time" />')).toBe(true);
    expect(catches('<UiInput type="datetime-local" />')).toBe(true);
    expect(catches('<NuxtInput type="month" />')).toBe(true);
    expect(catches('<input type="week">')).toBe(true);
    expect(catches(`<NuxtInput :type="step.type === 'date-range' ? 'date' : 'number'" />`)).toBe(true);
    expect(catches(`<NuxtInput :items="rows.map((r) => r.v)" type="date" />`)).toBe(true);
    expect(catches('<NuxtInput type="number" />')).toBe(false);
    expect(catches('<NuxtInput type="search" />')).toBe(false);
    expect(catches('<UiDateField v-model="day" />')).toBe(false);
    expect(catches('<NuxtInputDate v-model="day" />')).toBe(false);
  });

  it("o kit é quem serve /api/v1/** das oito superfícies", () => {
    expect(existsSync(resolve(surfacesDir, "operator-kit/server/api/v1/[...path].ts"))).toBe(true);
  });
});

describe("operator-kit: os primitivos respeitam o token de alvo de toque", () => {
  // `--spacing-control: 2.75rem` (44 px) vive no operator-theme.css. O literal
  // equivalente (`size-11`/`h-11`) renderiza igual HOJE e some no dia em que o token
  // mudar; foi assim que a cópia do Marketing acabou com um chip de `h-9` (36 px).
  const TOKENLESS = /\b(?:size|h|min-h)-(?:9|10|11)\b/;

  // Comentário fora ANTES de medir: o próprio cabeçalho destes arquivos CITA o `h-9`
  // que a cópia tinha, e citar a dívida não é cometê-la.
  const stripComments = (text: string): string =>
    text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "").replace(/<!--[\s\S]*?-->/g, "");

  // Barra e escolha juntos: o interruptor entrou com um alvo de 24 px vindo do PDV,
  // e o que cobra os dois é a mesma régua.
  for (const name of [
    ...KIT_OWNED_TOOLBAR_PRIMITIVES,
    ...KIT_OWNED_CHOICE_PRIMITIVES,
    ...KIT_OWNED_TEMPORAL_PRIMITIVES,
  ]) {
    it(`Ui${name} usa *-control, nunca altura literal`, () => {
      const direct = resolve(surfacesDir, "operator-kit/app/components", `Ui${name}.vue`);
      const nested = resolve(surfacesDir, "operator-kit/app/components/Ui", name, `${name}.vue`);
      const source = readFileSync(existsSync(direct) ? direct : nested, "utf8");
      expect(TOKENLESS.test(stripComments(source)), `Ui${name} voltou a cravar altura literal em vez do token`).toBe(false);
    });
  }

  it("o alvo de toque canônico continua em 44 px no tema central", () => {
    const theme = readFileSync(resolve(surfacesDir, "operator-kit/app/assets/css/operator-theme.css"), "utf8");
    expect(theme).toMatch(/--spacing-control:\s*2\.75rem;/);
  });

  // DECISÃO MUDOU (WP-OPERADOR-NUXTUI-ONDAS, onda 0, 08/10/2026): esta trava proibia
  // qualquer `@media (pointer: coarse)` no tema, e com isso consagrou a remoção, no
  // snapshot WIP do Gestor, do degrau de 48 px que o PDV, a Cozinha e a Produção usam
  // em tablet touch. O brief da migração manda o kit mudar só por opt-in até cada app
  // migrar. O que a trava protege continua protegido: o tema NÃO infla controle por
  // seletor de elemento. Ele só escala o token opt-in (`--spacing-control`), que vale
  // apenas onde o componente pede `min-h-control`.
  it("no ponteiro touch, o tema só escala o token opt-in; nunca infla controle por seletor", () => {
    const theme = readFileSync(resolve(surfacesDir, "operator-kit/app/assets/css/operator-theme.css"), "utf8");
    const coarseBlocks = [...theme.matchAll(/@media\s*\(pointer:\s*coarse\)[^{]*\{([\s\S]*?)\n\}/g)].map((m) => m[1]!);
    expect(coarseBlocks).toHaveLength(1);
    // Só sob o marcador da suíte (os sete apps não migrados) e no catálogo do kit; o
    // Gestor não veste nenhum dos dois.
    expect(coarseBlocks[0]).toMatch(/^\s*:root:has\(\[data-suite="v3"\], \[data-operator-catalog\]\)\s*\{\s*--spacing-control:\s*3rem;\s*\}\s*$/);
    expect(theme).not.toMatch(/@media\s*\(pointer:\s*coarse\)[^{]*\{[^}]*\b(?:button|input|select|textarea)\b/);
  });
});
