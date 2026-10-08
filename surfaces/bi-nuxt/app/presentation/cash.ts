// Caixa (a auditoria do Dono): o que a tela mostra, montado sem Vue.
//
// Os gráficos são do kit (`OperatorReadingChart`); daqui saem os pontos, as séries e o
// CSV de cada quadro (`OperatorReadingCard`). As tabelas leem as linhas do relatório
// como vêm; o CSV delas também sai daqui, com número cru (quem abre o CSV faz conta).
import type {
  BICashAccountRow,
  BICashDay,
  BICashDrawerRow,
  BICashHourRow,
  BICashMethodRow,
  BICashOperatorRow,
} from "~/generated/biContract";
import {
  readingCsvMoney,
  type ReadingChartPoint,
  type ReadingChartSeries,
  type ReadingCsv,
  type ReadingDivergingLabels,
} from "../../../operator-kit/app/presentation/readingChart";
import { BUCKET_SPAN_LABELS, bucketLabel, bucketRows, csvMoney, reais } from "./bi";

/** Segundos em linguagem de balcão: ninguém lê "184 s". */
export function formatDuration(seconds: number): string {
  if (!seconds) return "0 s";
  if (seconds < 60) return `${seconds} s`;
  const min = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (min < 60) return rest ? `${min} min ${rest} s` : `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
}

// ── Quebra por dia ─────────────────────────────────────────────────────────

/**
 * A primeira série é a que o divergente desenha (contado menos esperado). As outras
 * três vão no CSV do quadro: era o que o antigo tooltip dizia de cada dia.
 */
export const CASH_DIFFERENCE_SERIES: ReadingChartSeries[] = [
  { key: "difference", label: "Quebra (R$)" },
  { key: "shifts", label: "Turnos fechados" },
  { key: "sangria", label: "Sangrias (R$)" },
  { key: "suprimento", label: "Suprimentos (R$)" },
];

export const CASH_DIFFERENCE_SIDES: ReadingDivergingLabels = {
  positive: "Sobrou",
  negative: "Faltou",
  zero: "Fechou certo",
};

/** O nome do eixo diz o grão: série longa agrega por semana ou por mês. */
export function cashDifferenceAxis(days: readonly BICashDay[]): string {
  const span = bucketRows(days)[0]?.span ?? "day";
  return span === "day" ? "Dia" : span === "week" ? "Semana" : "Mês";
}

/** Um ponto por balde. Dinheiro em reais: o gráfico do kit recebe reais (`readingMoneyFormat`). */
export function cashDifferencePoints(days: readonly BICashDay[]): ReadingChartPoint[] {
  return bucketRows(days).map((bucket) => {
    const sum = (pick: (day: BICashDay) => number) => bucket.rows.reduce((total, day) => total + pick(day), 0);
    return {
      label: [bucketLabel(bucket.date, bucket.span), BUCKET_SPAN_LABELS[bucket.span]].filter(Boolean).join(" "),
      values: {
        difference: reais(sum((day) => day.difference_q)),
        shifts: sum((day) => day.shifts),
        sangria: reais(sum((day) => day.sangria_q)),
        suprimento: reais(sum((day) => day.suprimento_q)),
      },
    };
  });
}

/**
 * O CSV do quadro da quebra. Não é o `readingChartCsv(..., { money: true })` porque o
 * quadro mistura dinheiro (quebra, sangrias, suprimentos) e contagem (turnos): o
 * dinheiro sai como o do kit ("1500,50"), a contagem como número.
 */
export function cashDifferenceCsv(axisLabel: string, points: readonly ReadingChartPoint[]): ReadingCsv {
  const money = new Set(["difference", "sangria", "suprimento"]);
  return {
    header: [axisLabel, ...CASH_DIFFERENCE_SERIES.map((item) => item.label)],
    rows: points.map((point) => [
      point.label,
      ...CASH_DIFFERENCE_SERIES.map((item) => {
        const value = point.values[item.key];
        if (typeof value !== "number") return "";
        return money.has(item.key) ? readingCsvMoney(value) : value;
      }),
    ]),
  };
}

// ── Gaveta por hora ────────────────────────────────────────────────────────

/**
 * As duas barras de cada hora: abertura sem venda (o gesto do balcão) e destrave por
 * gerente (a exceção, em outra cor para se ler separada).
 */
export const DRAWER_HOUR_SERIES: ReadingChartSeries[] = [
  { key: "openings", label: "Aberturas sem venda" },
  { key: "unlocks", label: "Destraves por gerente", tone: "warning" },
];

/** O CSV leva também o que a trava contou em cada hora. */
export const DRAWER_HOUR_CSV_SERIES: ReadingChartSeries[] = [
  ...DRAWER_HOUR_SERIES,
  { key: "blocks", label: "Vezes travado" },
  { key: "open_seconds", label: "Gaveta aberta (s)" },
];

export function drawerHourPoints(rows: readonly BICashHourRow[]): ReadingChartPoint[] {
  return rows.map((row) => ({
    label: `${String(row.hour).padStart(2, "0")}h`,
    values: {
      openings: row.drawer_openings,
      unlocks: row.drawer_unlocks,
      blocks: row.blocks,
      open_seconds: row.open_seconds,
    },
  }));
}

// ── Meios de pagamento ─────────────────────────────────────────────────────

export interface CashMethodRow {
  method: string;
  amount_q: number;
  /** Fatia do total, de 0 a 100, para a barra da célula. */
  share: number;
  /** A fatia escrita ("42%"): a barra sozinha não basta. */
  shareLabel: string;
}

export function cashMethodRows(rows: readonly BICashMethodRow[]): CashMethodRow[] {
  const total = rows.reduce((sum, row) => sum + Math.max(row.amount_q, 0), 0);
  return rows.map((row) => {
    const share = total ? Math.round((Math.max(row.amount_q, 0) / total) * 100) : 0;
    return { method: row.method, amount_q: row.amount_q, share, shareLabel: `${share}%` };
  });
}

// ── CSV das tabelas ────────────────────────────────────────────────────────

export function operatorCsv(rows: readonly BICashOperatorRow[]): ReadingCsv {
  return {
    header: ["Operador", "Turnos", "Quebra (R$)", "Gaveta sem venda", "Destraves", "Pedidos de troco"],
    rows: rows.map((row) => [
      row.operator,
      row.shifts,
      csvMoney(row.difference_q),
      row.drawer_openings,
      row.drawer_unlocks,
      row.change_requests,
    ]),
  };
}

export function drawerCsv(rows: readonly BICashDrawerRow[]): ReadingCsv {
  return {
    header: [
      "Operador",
      "Travou",
      "Aberta no total (s)",
      "Pior episódio (s)",
      "Desistiu",
      "Destraves",
      "Buscou o PIN",
      "Sensor mudo",
      "Esquecida",
    ],
    rows: rows.map((row) => [
      row.operator,
      row.blocks,
      row.open_seconds,
      row.longest_open_seconds,
      row.dismissals,
      row.overrides,
      row.unlock_attempts,
      row.sensor_blind,
      row.left_open,
    ]),
  };
}

export function methodsCsv(rows: readonly CashMethodRow[]): ReadingCsv {
  return {
    header: ["Meio de pagamento", "Valor (R$)", "Fatia (%)"],
    rows: rows.map((row) => [row.method, csvMoney(row.amount_q), row.share]),
  };
}

export function openAccountsCsv(rows: readonly BICashAccountRow[]): ReadingCsv {
  return {
    header: ["Cliente", "Em aberto (R$)"],
    rows: rows.map((row) => [row.customer_name, csvMoney(row.balance_q)]),
  };
}
