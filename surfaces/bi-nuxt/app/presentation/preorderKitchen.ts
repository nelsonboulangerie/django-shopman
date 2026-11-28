// Encomendas na Cozinha: os dois tempos de cada encomenda (decisão do dono, 09/11/2026).
// Chegar à Cozinha não é começar: a espera vai da chegada ao "Iniciar", o preparo do
// "Iniciar" ao "Pronto". A projection já mede; aqui só as frases e a forma da tabela.
// Tempo que não houve fica escrito ("Ainda não iniciada"), nunca zero.
import type { BIPreorderKitchenReport, BIPreorderKitchenRow } from "~/types/bi";
import type { ReadingCsv } from "../../../operator-kit/app/presentation/readingChart";
import { formatInt } from "~/presentation/bi";

/** 12.5 → "12,5 min"; sem medida → "Sem medida". */
export function minutesLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Sem medida";
  return `${String(value).replace(".", ",")} min`;
}

/** ISO com fuso → "14/11 16:15", na hora da loja que o servidor já gravou. */
export function momentLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const [day, clock] = iso.split("T");
  const [, month, dd] = (day ?? "").split("-");
  return `${dd}/${month} ${(clock ?? "").slice(0, 5)}`;
}

/** A resposta em uma frase: quanto a encomenda espera e quanto leva, na mediana. */
export function preorderKitchenAnswer(
  report: Pick<BIPreorderKitchenReport, "orders" | "wait_median_minutes" | "prep_median_minutes">,
): string {
  if (!report.orders) return "Nenhuma encomenda chegou à Cozinha no período.";
  if (report.wait_median_minutes === null) return "Nenhuma encomenda do período foi iniciada ainda.";
  const wait = `esperou ${minutesLabel(report.wait_median_minutes)} pelo Iniciar`;
  if (report.prep_median_minutes === null) return `Na mediana, a encomenda ${wait}.`;
  return `Na mediana, a encomenda ${wait} e ficou pronta ${minutesLabel(report.prep_median_minutes)} depois.`;
}

/** "8 iniciadas, 6 prontas": quantas já têm cada tempo. */
export function startedHint(report: Pick<BIPreorderKitchenReport, "started" | "ready">): string {
  const started = `${formatInt(report.started)} ${report.started === 1 ? "iniciada" : "iniciadas"}`;
  const ready = `${formatInt(report.ready)} ${report.ready === 1 ? "pronta" : "prontas"}`;
  return `${started}, ${ready}`;
}

export interface PreorderKitchenLine {
  ref: string;
  released: string;
  started: string;
  ready: string;
  wait: string;
  prep: string;
}

export function preorderKitchenLines(rows: readonly BIPreorderKitchenRow[]): PreorderKitchenLine[] {
  return rows.map((row) => ({
    ref: row.ref,
    released: momentLabel(row.released_at),
    started: row.started_at ? momentLabel(row.started_at) : "Ainda não iniciada",
    ready: row.ready_at ? momentLabel(row.ready_at) : row.started_at ? "Ainda não pronta" : "",
    wait: row.wait_minutes === null ? "" : minutesLabel(row.wait_minutes),
    prep: row.prep_minutes === null ? "" : minutesLabel(row.prep_minutes),
  }));
}

export function preorderKitchenCsv(rows: readonly BIPreorderKitchenRow[]): ReadingCsv {
  return {
    header: ["Encomenda", "Chegou à Cozinha", "Iniciada", "Pronta", "Espera (min)", "Preparo (min)"],
    rows: rows.map((row) => [
      row.ref,
      row.released_at,
      row.started_at ?? "",
      row.ready_at ?? "",
      row.wait_minutes ?? "",
      row.prep_minutes ?? "",
    ]),
  };
}
