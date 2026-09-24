// O toggle "Ativo" dos cards da aba Canais — regras puras do modal, testáveis sem
// runtime. O servidor manda as opções de período (já filtradas pelo horário da
// loja), os motivos do tipo de canal e o que o gesto faz; aqui mora só o rascunho
// do modal: o que falta escolher, o rótulo do botão e o período no calendário.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md).
import type { ChannelSwitchProjection } from "~/types/feeds";
import type { ChannelSwitchRequest } from "~/composables/useFeedBoard";

export const CUSTOM_PERIOD = "custom";

export interface ChannelSwitchDraft {
  period: string;
  reason: string;
  /** "AAAA-MM-DD" do calendário; vazio até escolher. */
  startDate: string;
  endDate: string;
  /** "HH:MM" */
  startTime: string;
  endTime: string;
}

export function emptyDraft(): ChannelSwitchDraft {
  return { period: "", reason: "", startDate: "", endDate: "", startTime: "00:00", endTime: "00:00" };
}

/** O instante local "AAAA-MM-DDTHH:MM" em ISO com o fuso do dispositivo. */
function localIso(date: string, time: string): string {
  const parsed = new Date(`${date}T${time || "00:00"}:00`);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

/** O que ainda falta para confirmar — a primeira pendência, em uma frase. */
export function missingStep(sw: ChannelSwitchProjection, draft: ChannelSwitchDraft, now: Date = new Date()): string {
  const option = sw.periods.find((item) => item.key === draft.period);
  if (!option || !option.enabled) return "Escolha por quanto tempo.";
  if (draft.period === CUSTOM_PERIOD) {
    if (!draft.startDate || !draft.endDate) return "Escolha no calendário quando começa e quando termina.";
    const start = new Date(localIso(draft.startDate, draft.startTime));
    const end = new Date(localIso(draft.endDate, draft.endTime));
    if (!(end.getTime() > start.getTime())) return "O fim precisa vir depois do início.";
    if (end.getTime() <= now.getTime()) return "O fim do período já passou.";
  }
  if (sw.reason_required && !draft.reason.trim()) return "Escolha ou escreva o motivo.";
  return "";
}

/** O corpo do pedido ao servidor. */
export function switchRequest(sw: ChannelSwitchProjection, draft: ChannelSwitchDraft): ChannelSwitchRequest {
  const request: ChannelSwitchRequest = { is_active: !sw.is_active, period: draft.period, reason: draft.reason.trim() };
  if (draft.period === CUSTOM_PERIOD) {
    request.starts_at = localIso(draft.startDate, draft.startTime);
    request.ends_at = localIso(draft.endDate, draft.endTime);
  }
  return request;
}

/** O verbo do botão: o gesto que ele faz — "Desligar", "Ligar" ou, no futuro, "Agendar". */
export function confirmLabel(sw: ChannelSwitchProjection, draft: ChannelSwitchDraft, now: Date = new Date()): string {
  if (draft.period === CUSTOM_PERIOD && draft.startDate) {
    const start = new Date(localIso(draft.startDate, draft.startTime));
    if (start.getTime() > now.getTime()) return sw.is_active ? "Agendar o desligamento" : "Agendar a religação";
  }
  return sw.is_active ? "Desligar" : "Ligar";
}

// ── Calendário ────────────────────────────────────────────────────────────────

export interface CalendarDay {
  iso: string; // AAAA-MM-DD
  day: number;
  inMonth: boolean;
  past: boolean;
}

const pad = (value: number) => String(value).padStart(2, "0");
export const isoDay = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** As semanas do mês (domingo a sábado), com os dias de borda dos meses vizinhos. */
export function monthWeeks(year: number, month: number, today: Date = new Date()): CalendarDay[][] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  const todayIso = isoDay(today);
  const weeks: CalendarDay[][] = [];
  for (let week = 0; week < 6; week += 1) {
    const days: CalendarDay[] = [];
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + week * 7 + weekday);
      const iso = isoDay(date);
      days.push({ iso, day: date.getDate(), inMonth: date.getMonth() === month, past: iso < todayIso });
    }
    if (week >= 4 && days.every((day) => !day.inMonth)) break;
    weeks.push(days);
  }
  return weeks;
}

/** Um toque no calendário: o primeiro marca o início; o segundo, o fim (ou recomeça). */
export function pickDay(draft: ChannelSwitchDraft, iso: string): Pick<ChannelSwitchDraft, "startDate" | "endDate"> {
  if (!draft.startDate || draft.endDate || iso < draft.startDate) return { startDate: iso, endDate: "" };
  return { startDate: draft.startDate, endDate: iso };
}

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
export const monthLabel = (year: number, month: number) => `${MONTHS[month]} de ${year}`;

/** A janela escolhida em uma linha: "de sáb. 20/12 às 0h a seg. 5/1 às 0h". */
export function rangeLine(draft: ChannelSwitchDraft): string {
  if (!draft.startDate) return "";
  const when = (date: string, time: string) => {
    const [year, month, day] = date.split("-").map(Number);
    const parsed = new Date(year!, month! - 1, day!);
    const weekday = ["dom.", "seg.", "ter.", "qua.", "qui.", "sex.", "sáb."][parsed.getDay()];
    const [hour, minute] = (time || "00:00").split(":");
    const clock = minute === "00" ? `${Number(hour)}h` : `${Number(hour)}h${minute}`;
    return `${weekday} ${day}/${month} às ${clock}`;
  };
  const start = `de ${when(draft.startDate, draft.startTime)}`;
  return draft.endDate ? `${start} a ${when(draft.endDate, draft.endTime)}` : `${start} — escolha quando termina`;
}
