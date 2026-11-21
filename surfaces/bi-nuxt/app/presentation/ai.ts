// A seção IA do B.I. (DEV-2026-067): quanto a casa gasta com IA, por papel e por modelo,
// a pauta da conferência antes do envio e as respostas que caíram na alternativa segura.
// Só do Dono, só leitura. Dinheiro de IA é em micro-dólar INTEIRO (`*_usd_micros`, o
// medidor da porta de IA, `AiInvocation`): o custo da API é em dólar e o sufixo `_q`
// (centavo de real) mentiria. A tela formata; a conta nunca passa por número quebrado.

export interface BIAiSpendRow {
  purpose: string;
  purpose_label: string;
  model: string;
  calls: number;
  errors: number;
  denied: number;
  cost_usd_micros: number;
  /** Alguma chamada da linha usou modelo fora da tabela de preço (contado pelo mais caro). */
  estimated: boolean;
}

export interface BIAiSpendDay {
  date: string;
  cost_usd_micros: number;
}

export interface BIAiReason {
  reason: string;
  label: string;
  count: number;
}

export interface BIAiGap {
  /** A pergunta do cliente, redigida (sem nome, contato, documento ou endereço). */
  question: string;
  count: number;
  last_at: string;
  /** O Admin, onde a resposta vira pergunta frequente (no B.I. não há ação). */
  admin_url: string;
}

export interface BIAiFallback {
  at: string;
  conversation_id: number;
  customer_text: string;
  reply_text: string;
  reasons: string[];
  admin_url: string;
}

export interface BIAiReport {
  /** `shadow`: a conferência só mede, a resposta original saiu. `enforce`: a alternativa saiu. */
  conference_mode: "shadow" | "enforce";
  spend: {
    cost_usd_micros: number;
    calls: number;
    errors: number;
    denied: number;
    estimated_calls: number;
    rows: BIAiSpendRow[];
    days: BIAiSpendDay[];
  };
  conference: {
    conferred: number;
    would_fall: number;
    reasons: BIAiReason[];
    gaps: BIAiGap[];
  };
  fallbacks: BIAiFallback[];
}

const MICROS_PER_USD = 1_000_000;

/** "US$ 1,2345": quatro casas, porque uma chamada custa frações de centavo de dólar. */
export function formatUsdMicros(micros: number): string {
  const usd = micros / MICROS_PER_USD;
  return `US$ ${usd.toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;
}

/** O valor do CSV: dólar com ponto, sem arredondar o micro. */
export function csvUsdMicros(micros: number): string {
  return (micros / MICROS_PER_USD).toFixed(6);
}

export function perCall(micros: number, calls: number): number {
  return calls > 0 ? Math.round(micros / calls) : 0;
}

export function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

/** A resposta do topo, numa frase. */
export function aiAnswer(report: BIAiReport): string {
  const { spend, conference } = report;
  if (!spend.calls && !conference.conferred) return "Nenhum uso de IA no período";
  const spent = `${formatUsdMicros(spend.cost_usd_micros)} em ${spend.calls.toLocaleString("pt-BR")} chamadas`;
  if (!conference.conferred) return spent;
  return `${spent}; ${percent(conference.would_fall, conference.conferred)} das respostas reprovadas na conferência`;
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
