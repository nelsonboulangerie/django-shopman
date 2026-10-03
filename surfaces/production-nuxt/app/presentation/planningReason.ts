// Presentation: o "Por quê" do Planejamento (SUITE-UX UX-P2, L3).
//
// A linha mostra só o número sugerido e, no máximo, UM sinal. A conta inteira
// mora no detalhe que abre por cima da linha. Tudo aqui é transformação pura do
// `ProductionSuggestionProjection`: o backend já entrega a conta fechada
// (`projected + committed + margin = quantity`), os dias que esgotaram, a sobra
// e a falta de insumo; esta camada só escolhe as palavras e o que mostrar.
//
// Regra do sinal único (uma prioridade, nunca dois selos na linha):
//   1. falta insumo: o número não sai do forno como está, e o fechamento vai
//      recusar (mesma régua do guardrail). É o único que muda o que é possível.
//   2. acabou cedo: esgotou em metade ou mais dos dias usados na conta. A
//      procura é maior do que a venda mostrou.
//   3. sobra: a sobra passou do teto que a fórmula desconta (15%). Abaixo dele
//      a sobra não mexeu no número, e avisar seria ruído.
import type {
  ProductionSuggestionProjection,
  SuggestionMaterialShortageProjection,
} from "~/types/production";

export type SuggestionSignalKind = "material" | "soldout" | "leftover";

export interface SuggestionSignal {
  kind: SuggestionSignalKind;
  label: string;
  icon: string;
  tone: "danger" | "warning";
}

const SIGNALS: Record<SuggestionSignalKind, SuggestionSignal> = {
  material: {
    kind: "material",
    label: "falta insumo",
    icon: "lucide:lock",
    tone: "warning",
  },
  soldout: {
    kind: "soldout",
    label: "acabou cedo",
    icon: "lucide:clock-alert",
    tone: "danger",
  },
  leftover: {
    kind: "leftover",
    label: "sobra",
    icon: "lucide:archive",
    tone: "warning",
  },
};

/** Esgotou em metade ou mais dos dias da amostra. */
export function soldOutOften(s: ProductionSuggestionProjection): boolean {
  return s.soldout_days > 0 && s.soldout_days * 2 >= s.sample_size;
}

/** O sinal único da linha, ou `null` quando não há nada a notar. */
export function suggestionSignal(
  s: ProductionSuggestionProjection | null | undefined,
): SuggestionSignal | null {
  if (!s) return null;
  if (s.material_shortages.length) return SIGNALS.material;
  if (soldOutOften(s)) return SIGNALS.soldout;
  if (s.waste_discounted) return SIGNALS.leftover;
  return null;
}

export const SIGNAL_CHIP: Record<SuggestionSignal["tone"], string> = {
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
  warning: "border-warning/40 bg-warning/10 text-warning",
};

// ── Dia da semana da data planejada ────────────────────────────────────────

const WEEKDAY_SINGULAR = [
  "domingo",
  "segunda",
  "terça",
  "quarta",
  "quinta",
  "sexta",
  "sábado",
] as const;

const WEEKDAY_PLURAL = [
  "domingos",
  "segundas",
  "terças",
  "quartas",
  "quintas",
  "sextas",
  "sábados",
] as const;

function weekdayIndex(isoDate: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return null;
  const day = new Date(Date.UTC(+match[1]!, +match[2]! - 1, +match[3]!));
  return Number.isNaN(day.getTime()) ? null : day.getUTCDay();
}

/**
 * Como chamar os dias da amostra: "sábados" quando a conta só olha o mesmo
 * dia da semana da data planejada; "dias" quando olha todos.
 */
export function sampleDaysWord(
  s: ProductionSuggestionProjection,
  isoDate: string,
): { one: string; many: string } {
  const index = weekdayIndex(isoDate);
  if (s.same_weekday && index != null) {
    return { one: WEEKDAY_SINGULAR[index]!, many: WEEKDAY_PLURAL[index]! };
  }
  return { one: "dia", many: "dias" };
}

// ── A conta ────────────────────────────────────────────────────────────────

export interface ReasonTerm {
  value: string;
  label: string;
}

export interface ReasonMath {
  terms: ReasonTerm[];
  total: ReasonTerm;
  /** O que a margem carrega: "segurança 10%", o reforço do dia. */
  marginNote: string;
}

function asNumber(value: string): number {
  return Number.parseFloat(value.replace(",", ".")) || 0;
}

function display(value: string): string {
  return value.replace(".", ",");
}

/**
 * `projeção + encomendas + margem = sugestão`, nos termos que a fórmula usa:
 * média de venda (do mesmo dia da semana quando é o caso), encomendas já
 * confirmadas e margem. Encomenda zero sai da conta; a margem fica sempre,
 * porque é ela que explica a diferença.
 */
export function suggestionMath(
  s: ProductionSuggestionProjection,
  isoDate: string,
): ReasonMath {
  const days = sampleDaysWord(s, isoDate);
  const terms: ReasonTerm[] = [
    {
      value: display(s.projected),
      label: days.many === "dias" ? "média de venda" : `média dos ${days.many}`,
    },
  ];
  if (asNumber(s.committed) > 0) {
    terms.push({ value: display(s.committed), label: "encomendas" });
  }
  terms.push({ value: display(s.margin), label: "margem" });

  const notes: string[] = [];
  if (s.safety_percent > 0) notes.push(`segurança ${s.safety_percent}%`);
  if (s.high_demand_applied) {
    const index = weekdayIndex(isoDate);
    notes.push(
      index === 5 || index === 6
        ? `reforço de ${WEEKDAY_SINGULAR[index]}`
        : "reforço de sexta e sábado",
    );
  }
  return {
    terms,
    total: { value: display(s.quantity), label: "sugestão" },
    marginNote: notes.join(" + "),
  };
}

// ── O histórico curto ──────────────────────────────────────────────────────

export interface ReasonHistoryLine {
  kind: "soldout" | "leftover" | "season";
  text: string;
  /** Nota curta logo abaixo, quando a fórmula já tratou o fato. */
  note: string;
}

export function suggestionHistory(
  s: ProductionSuggestionProjection,
  isoDate: string,
): ReasonHistoryLine[] {
  const days = sampleDaysWord(s, isoDate);
  const lines: ReasonHistoryLine[] = [];
  if (s.soldout_days > 0 && s.sample_size > 0) {
    lines.push({
      kind: "soldout",
      text: `Acabou antes de fechar em ${s.soldout_days} dos ${s.sample_size} ${days.many} usados na conta`,
      note: "",
    });
  }
  if (s.waste_percent > 0) {
    lines.push({
      kind: "leftover",
      text: `Sobrou ${s.waste_percent}% do que vendeu`,
      note: s.waste_discounted ? "a média já desconta essa sobra" : "",
    });
  }
  if (s.season_label) {
    lines.push({
      kind: "season",
      text: `Histórico só da ${s.season_label}`,
      note: "",
    });
  }
  return lines;
}

/** "confiança média · 4 sábados de histórico" (o subtítulo do detalhe). */
export function suggestionBasisLine(
  s: ProductionSuggestionProjection,
  isoDate: string,
): string {
  const days = sampleDaysWord(s, isoDate);
  const parts = [`confiança ${s.confidence.toLowerCase()}`];
  if (s.sample_size > 0) {
    parts.push(
      `${s.sample_size} ${s.sample_size === 1 ? days.one : days.many} de histórico`,
    );
  }
  return parts.join(" · ");
}

// ── A falta de insumo ──────────────────────────────────────────────────────

/** "Manteiga: dá para 40; faltam 1200 g". */
export function shortageLine(
  item: SuggestionMaterialShortageProjection,
): string {
  return `${item.name}: dá para ${display(item.fits_quantity)}; faltam ${item.missing_display}`;
}

/**
 * A alternativa que cabe no estoque, quando existe: um número inteiro maior
 * que zero e menor que a sugestão. Zero não é alternativa (não há o que
 * planejar); a sugestão inteira não falta.
 */
export function fittingAlternative(
  s: ProductionSuggestionProjection,
): string | null {
  if (!s.material_shortages.length || !s.fits_quantity) return null;
  const fits = asNumber(s.fits_quantity);
  if (fits <= 0 || fits >= asNumber(s.quantity)) return null;
  return s.fits_quantity;
}
