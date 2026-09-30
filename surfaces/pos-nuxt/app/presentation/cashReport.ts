// Presentation — relatório de sessão de caixa (leituras X/Z + histórico).
//
// Transforms puras sobre a CashSessionReport: horário/período do turno, o
// sinal do movimento de gaveta (entrada/saída) e o display assinado. BLIND: o
// contrato nunca traz o esperado da gaveta; nada aqui deriva ou reconstitui a
// conferência (espírito do comentário em presentation/cash.ts).

import type { CashMovementRow, ShiftReading } from "~/types/cashReport";
import { formatBRL } from "~/utils/posIntent";

// Fuso da loja fixado: a leitura X/Z é sempre lida no horário do balcão, não no
// do servidor. Sem isto, o mesmo instante vira "08:02" no dev (BRT) e "11:02" na
// CI (UTC) — o teste de fuso quebrava por isso. Espírito de localdate_not_now_date.
const STORE_TIME_ZONE = "America/Sao_Paulo";

/** Hora curta (pt-BR) de um ISO datetime; "" quando ausente ou inválido. */
export function timeDisplay(raw: string | null | undefined): string {
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: STORE_TIME_ZONE,
      });
}

/** Período do turno: "08:02 às 12:30" fechado, "desde 08:02" aberto. */
export function shiftPeriodDisplay(reading: Pick<ShiftReading, "opened_at" | "closed_at">): string {
  const opened = timeDisplay(reading.opened_at);
  const closed = timeDisplay(reading.closed_at);
  if (!opened) return "";
  return closed ? `${opened} às ${closed}` : `desde ${opened}`;
}

/**
 * Direção do movimento na gaveta: suprimento entra, sangria sai. O valor é
 * sempre positivo — o sinal vive no tipo.
 */
export function movementFlow(movement: Pick<CashMovementRow, "kind" | "amount_q">): "in" | "out" {
  if (movement.kind === "suprimento") return "in";
  return "out";
}

/** Valor do movimento com sinal explícito: "+R$ 10,00" / "-R$ 20,00". */
export function signedMovementDisplay(movement: Pick<CashMovementRow, "kind" | "amount_q">): string {
  const sign = movementFlow(movement) === "in" ? "+" : "-";
  return `${sign}${formatBRL(Math.abs(movement.amount_q))}`;
}

/** Título da leitura: X (parcial, turno aberto) ou Z (turno fechado). */
export function readingTitle(reading: Pick<ShiftReading, "status" | "shift_id">): string {
  return reading.status === "open"
    ? `Leitura X · turno #${reading.shift_id}`
    : `Leitura Z · turno #${reading.shift_id}`;
}

/** O que a tela do relatório diz quando o servidor recusa a leitura pela estação. */
export interface CashReportStationRefusal {
  title: string;
  message: string;
}

/**
 * A leitura X é da gaveta da ESTAÇÃO: o servidor recusa com 409 quando o balcão
 * pedido não é o deste dispositivo (`pos_terminal_mismatch`) ou quando o
 * dispositivo não é um balcão (`pos_station_required`). Nenhum dos dois é
 * "deu erro": o operador precisa saber que está no balcão errado.
 */
export function cashReportStationRefusal(status: number | undefined, code: string): CashReportStationRefusal | null {
  if (status !== 409) return null;
  if (code === "pos_terminal_mismatch") {
    return {
      title: "Este relatório é de outro balcão",
      message:
        "Este dispositivo está ligado a um balcão diferente do que a tela pediu. A leitura X mostra só a gaveta do balcão onde você está. Volte à sessão de caixa e abra o relatório de novo.",
    };
  }
  if (code === "pos_station_required") {
    return {
      title: "Este dispositivo não é um balcão",
      message:
        "A leitura X é da gaveta de um balcão, e este dispositivo não foi iniciado como balcão. Abra o relatório no dispositivo do balcão.",
    };
  }
  return null;
}
