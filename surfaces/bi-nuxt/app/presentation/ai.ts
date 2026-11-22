// A seção IA do B.I. (DEV-2026-067): quanto a casa gasta com IA, por papel e por modelo,
// a pauta da conferência antes do envio e as respostas que caíram na alternativa segura.
// Só do Dono, só leitura. O medidor guarda micro-dólar INTEIRO; o B.I. diz em reais pela
// PTAX de venda do dia (decisão de 21/11/2026), e a cotação usada vem junto, por dia.
// A tela formata: total com 2 casas, custo por chamada com 4. A conta nunca passa por
// número quebrado; o CSV leva os dois (US$ com 6 casas e R$) e a cotação.
import { formatDateClock } from "../../../operator-kit/app/presentation/clock";
import { STORE_TIME_ZONE } from "../../../operator-kit/app/presentation/dates";
import type { BIAiReport, BIAiSpendRow } from "~/types/bi";

const MICROS = 1_000_000;

function brl(micros: number, digits: 2 | 4): string {
  return (micros / MICROS).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function usd(micros: number, digits: 2 | 4): string {
  const value = (micros / MICROS).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `US$ ${value}`;
}

/** Total em reais com 2 casas; sem cotação, o dólar, dito como dólar. */
export function formatSpend(brlMicros: number | null, usdMicros: number): string {
  return brlMicros === null ? usd(usdMicros, 2) : brl(brlMicros, 2);
}

/** Custo por chamada: frações de centavo, então 4 casas. */
export function formatPerCall(brlMicros: number | null, usdMicros: number, calls: number): string {
  if (!calls) return brlMicros === null ? usd(0, 4) : brl(0, 4);
  return brlMicros === null ? usd(Math.round(usdMicros / calls), 4) : brl(Math.round(brlMicros / calls), 4);
}

export function perCallSort(row: BIAiSpendRow): number {
  const base = row.cost_brl_micros ?? row.cost_usd_micros;
  return row.calls ? base / row.calls : 0;
}

/** O valor do CSV: dólar com 6 casas, sem arredondar o micro. */
export function csvUsd(micros: number): string {
  return (micros / MICROS).toFixed(6);
}

export function csvBrl(micros: number | null): string {
  return micros === null ? "" : (micros / MICROS).toFixed(4);
}

/** A cotação efetiva de uma linha que atravessa dias (R$ por US$, 4 casas). */
export function csvRate(brlMicros: number | null, usdMicros: number): string {
  return brlMicros === null || !usdMicros ? "" : (brlMicros / usdMicros).toFixed(4);
}

export function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

/** A resposta do topo, numa frase. */
export function aiAnswer(report: BIAiReport): string {
  if (!report.calls && !report.conferred) return "Nenhum uso de IA no período";
  const calls = report.calls === 1 ? "1 chamada" : `${report.calls.toLocaleString("pt-BR")} chamadas`;
  const spent = `${formatSpend(report.cost_brl_micros, report.cost_usd_micros)} em ${calls}`;
  if (!report.conferred) return spent;
  return `${spent}; ${percent(report.would_fall, report.conferred)} das respostas reprovadas na conferência`;
}

/** De onde vêm os reais: a PTAX de venda, e quando alguma cotação ainda pode mudar. */
export function quoteHint(report: BIAiReport): string {
  if (report.cost_brl_micros === null) return "Sem cotação do dólar para algum dia: total em dólar";
  const last = [...report.days].reverse().find((day) => day.rate);
  const rate = last?.rate ? ` (última: R$ ${Number(last.rate).toLocaleString("pt-BR", { minimumFractionDigits: 4 })})` : "";
  return report.provisional_quotes
    ? `Pela PTAX de venda do dia${rate}; a de hoje ainda pode mudar`
    : `Pela PTAX de venda do dia${rate}`;
}

export function conferenceHint(report: BIAiReport): string {
  return report.conference_mode === "shadow"
    ? "Em teste: a conferência só mede, e a resposta original foi enviada"
    : "A conferência vale: a reprovada não sai, vai a alternativa segura";
}

export function fallbacksTitle(report: BIAiReport): string {
  return report.conference_mode === "shadow"
    ? "Respostas que iriam para a alternativa segura"
    : "Respostas trocadas pela alternativa segura";
}

/** "21/11, 15h42": a hora da casa, pelo formatador da suíte. */
export function whenLabel(iso: string): string {
  return formatDateClock(iso, { day: "2-digit", month: "2-digit" }, { timeZone: STORE_TIME_ZONE });
}
