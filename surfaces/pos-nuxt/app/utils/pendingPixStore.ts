/**
 * Pix que ainda espera confirmação, guardado no dispositivo.
 *
 * O cliente 1 ainda está pagando quando o operador já atende o 2: o PDV acompanha
 * QUANTOS Pix estiverem abertos, e cada um até resolver (pago, cancelado/expirado
 * ou desistência). Recarregar a página não esquece nenhum: a lista mora no
 * `localStorage` da estação e volta ao abrir a tela.
 *
 * Só refs e a hora da cobrança: nada de cliente, valor ou QR. A verdade continua
 * no servidor (`pos/payment/<ref>/status/`); isto aqui é a lista do que perguntar.
 */

export const PENDING_PIX_STORAGE_KEY = "shopman:pos:pending-pix";

/** O mesmo teto do acompanhamento na tela de resultado: 240 × 2,5 s. */
export const PENDING_PIX_MAX_AGE_MS = 10 * 60 * 1000;

export interface PendingPix {
  orderRef: string;
  /** ISO da cobrança: a desistência conta a partir daqui, mesmo depois de recarregar. */
  since: string;
}

function isPendingPix(value: unknown): value is PendingPix {
  if (!value || typeof value !== "object") return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.orderRef === "string" && entry.orderRef !== ""
    && typeof entry.since === "string" && !Number.isNaN(Date.parse(entry.since));
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

/** Passou do teto: a próxima resposta sem confirmação vira desistência dita. */
export function pendingPixExpired(entry: PendingPix, now: number): boolean {
  return now - Date.parse(entry.since) >= PENDING_PIX_MAX_AGE_MS;
}
