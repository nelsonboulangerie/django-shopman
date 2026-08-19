// Presentation — operator lock (Opção C). Pure transforms over the operator
// session projection. The barcode badge scanner behaves like a keyboard that
// types the token fast and ends with Enter; the PIN is typed on an on-screen pad.
// No network here — the composable owns I/O; this owns shape + the unlock payload.
import type { OperatorSession } from "../types/operator";

/** The overlay shows only when the gate is on AND nobody is operating. When the
 *  gate is off (SHOPMAN_REQUIRE_ACTIVE_OPERATOR=false) the surface is never locked. */
export function isLocked(session: OperatorSession | null): boolean {
  return Boolean(session?.require_operator && session?.locked);
}

export function operatorName(session: OperatorSession | null): string {
  return session?.operator?.name || session?.operator?.username || "";
}

/**
 * O crachá tem 12 hexadecimais (doorman `issue_badge` = `token_hex(6)`).
 *
 * Serve para rotear a leitura para o destrave por crachá sem o operador escolher
 * modo nenhum: o leitor "digita" e a tela sabe que aquilo é um crachá.
 *
 * ⚠️ Eram 24, e o número encolheu por causa do PAPEL, não do software: 24
 * caracteres em Code 128 obrigavam barras de 0,25mm para caber num crachá
 * tamanho cartão, largura que não é múltiplo do ponto da impressora — o símbolo
 * saía distorcido e leitor nenhum lia. Com 12 a barra dobra de espessura na
 * mesma etiqueta.
 *
 * Este número e o `BADGE_BYTES` do doorman são a MESMA decisão em dois lados:
 * mexer num sem o outro faz a tela descartar crachá válido, calada, antes de
 * perguntar ao servidor.
 */
export function isLikelyBadge(value: string): boolean {
  return /^[0-9a-f]{12}$/i.test(value.trim());
}

/** Maior intervalo (ms) entre duas teclas que ainda conta como a MESMA passada de
 *  crachá. Um leitor HID emite o token inteiro em ~10-30ms por caractere; dedo
 *  humano no balcão não chega perto disso. Acima da janela, a leitura recomeça —
 *  é o que impede que teclas soltas ao longo do turno se somem num token falso. */
export const BADGE_MAX_GAP_MS = 120;

/** Acumula uma tecla no buffer do leitor, respeitando a janela de tempo.
 *
 * Puro de propósito: o intervalo entra como número (``gapMs``), então a regra de
 * tempo é testável sem timer nem relógio falso — quem mede o intervalo é o
 * chamador. Teclas não-imprimíveis (Shift, Tab, setas) não entram no buffer;
 * um intervalo acima da janela DESCARTA o que veio antes e recomeça nesta tecla.
 */
export function pushBadgeKey(
  buffer: string,
  key: string,
  gapMs: number,
  maxGapMs: number = BADGE_MAX_GAP_MS,
): string {
  if (key.length !== 1) return buffer; // "Shift", "Enter", "ArrowLeft"… não são conteúdo
  return gapMs > maxGapMs ? key : buffer + key;
}

export interface UnlockInput {
  operatorId?: number | string | null;
  pin?: string;
  badge?: string;
  perm?: string;
}

/** The POST body for operator/unlock/. Badge wins when present; otherwise the
 *  picked operator + typed PIN. ``perm`` (the surface capability) restricts who
 *  may unlock here. */
export function buildUnlockPayload(input: UnlockInput): Record<string, unknown> {
  const badge = (input.badge ?? "").trim();
  const perm = input.perm ? { perm: input.perm } : {};
  if (badge) {
    return { badge, ...perm };
  }
  return { operator_id: input.operatorId ?? "", pin: (input.pin ?? "").trim(), ...perm };
}

/** Whether the PIN entry is ready to submit (an operator picked + a non-trivial PIN). */
export function canSubmitPin(operatorId: number | null, pin: string): boolean {
  return operatorId != null && pin.trim().length >= 4;
}

/** Append a digit to the PIN buffer, capped (keypads shouldn't grow unbounded). */
export function appendPinDigit(pin: string, digit: string, max = 8): string {
  if (!/^[0-9]$/.test(digit)) return pin;
  return pin.length >= max ? pin : pin + digit;
}
