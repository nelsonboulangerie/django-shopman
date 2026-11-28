/**
 * Pix que ainda espera confirmação, guardado no dispositivo.
 *
 * O cliente 1 ainda está pagando quando o operador já atende o 2: o PDV acompanha
 * QUANTOS Pix estiverem abertos, e cada um até resolver (pago, cancelado/expirado
 * ou desistência). Recarregar a página não esquece nenhum: a lista mora no
 * `localStorage` da estação e volta ao abrir a tela.
 *
 * Só refs, a hora da cobrança e o prazo do Pix: nada de cliente, valor ou QR. A
 * verdade continua no servidor (`pos/payment/<ref>/status/`, que já diz
 * `is_terminal` quando o prazo venceu); isto aqui é a lista do que perguntar.
 *
 * O PRAZO é o do servidor: o `payment.expires_at` que o fechamento devolve, o
 * mesmo que o gateway carrega. Antes o PDV desistia sozinho aos 10 min, e o Pix de
 * prazo maior (o QR ainda válido, o cliente ainda pagando) virava "não confirmamos"
 * na tela. A desistência local só existe para quando o servidor some: o prazo do
 * Pix mais uma folga para o aviso do banco chegar.
 */

export const PENDING_PIX_STORAGE_KEY = "shopman:pos:pending-pix";

/**
 * Teto quando o servidor NÃO mandou o prazo (o gateway não devolveu `expires_at`):
 * a única constante que sobra, e só para o Pix sem prazo dito.
 */
export const PENDING_PIX_FALLBACK_MAX_AGE_MS = 10 * 60 * 1000;
/** Depois do prazo, quanto ainda se espera o aviso do banco (webhook) chegar. */
export const PENDING_PIX_GRACE_MS = 60 * 1000;

export interface PendingPix {
  orderRef: string;
  /** ISO da cobrança. */
  since: string;
  /** ISO do prazo do Pix, como o servidor disse (`payment.expires_at`). */
  expiresAt?: string;
}

function isPendingPix(value: unknown): value is PendingPix {
  if (!value || typeof value !== "object") return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.orderRef === "string" && entry.orderRef !== ""
    && typeof entry.since === "string" && !Number.isNaN(Date.parse(entry.since))
    && (entry.expiresAt === undefined
      || (typeof entry.expiresAt === "string" && !Number.isNaN(Date.parse(entry.expiresAt))));
}

export function readPendingPix(): PendingPix[] {
  try {
    const raw = globalThis.localStorage?.getItem(PENDING_PIX_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    return parsed.filter(isPendingPix).filter((entry) => {
      if (seen.has(entry.orderRef)) return false;
      seen.add(entry.orderRef);
      return true;
    });
  } catch {
    // silêncio-deliberado: sem storage a lista vive só na memória da aba, e o
    // acompanhamento segue igual enquanto a aba estiver aberta.
    return [];
  }
}

export function writePendingPix(entries: PendingPix[]): void {
  try {
    const storage = globalThis.localStorage;
    if (!storage) return;
    if (entries.length === 0) storage.removeItem(PENDING_PIX_STORAGE_KEY);
    else storage.setItem(PENDING_PIX_STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // silêncio-deliberado: idem `readPendingPix`.
  }
}

/**
 * Quando o PDV desiste de perguntar: o prazo do servidor mais a folga do aviso do
 * banco; sem prazo dito, o teto de reserva a partir da cobrança.
 */
export function pendingPixDeadlineMs(entry: Pick<PendingPix, "since" | "expiresAt">): number {
  const expires = entry.expiresAt ? Date.parse(entry.expiresAt) : Number.NaN;
  if (!Number.isNaN(expires)) return expires + PENDING_PIX_GRACE_MS;
  return Date.parse(entry.since) + PENDING_PIX_FALLBACK_MAX_AGE_MS;
}

/** Passou do prazo: a próxima resposta sem confirmação vira desistência dita. */
export function pendingPixExpired(entry: PendingPix, now: number): boolean {
  return now >= pendingPixDeadlineMs(entry);
}
