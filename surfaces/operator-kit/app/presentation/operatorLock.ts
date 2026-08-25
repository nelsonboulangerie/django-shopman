// Presentation — a trava do operador. Transforms puros sobre a projection da
// sessão. O leitor de crachá se comporta como um teclado que digita o token
// rápido e termina com Enter; o PIN é digitado num pad na tela. Sem rede aqui —
// o composable é dono do I/O; isto é dono da forma e do payload do destrave.
import type { OperatorSession } from "../types/operator";

/** A trava sobe quando ninguém está operando. Ponto.
 *
 * Havia um `require_operator` no meio: um interruptor de servidor que dizia se o
 * gate estava ligado, e com ele desligado a superfície NUNCA travava. Ele existia
 * porque as duas identidades conviviam e a segunda era opcional. Não há mais
 * interruptor: sem alguém identificado, não se opera. */
export function isLocked(session: OperatorSession | null): boolean {
  return Boolean(session?.locked);
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

// ── Captura de identificação: UM buffer, decisão no Enter ──────────────────
//
// Toda entrada da tela de identificação (tecla física OU toque no pad) entra num
// único buffer, NA HORA — nenhuma tecla é descartada no momento em que chega,
// então o PIN nunca "come" dígito de quem digita depressa. A pergunta "isto é um
// crachá ou é gente digitando?" só tem resposta confiável quando a rajada
// TERMINA: o leitor HID sempre fecha com Enter, e é no Enter que se decide.
//
// A régua é a CADÊNCIA INTERNA do rabo do buffer: um leitor emite ~10-30ms por
// caractere; o digitador humano mais ágil fica na casa dos 60-120ms. A mediana
// dos intervalos separa os dois mundos com folga — e, por ser mediana, um soluço
// de agendamento do USB no meio da passada não derruba a leitura. Classificar
// tecla a tecla por janela de tempo faria dedo rápido virar "crachá" e perderia
// dígito; aqui dedo nenhum é classificado como máquina.

/** O PIN visível para no oitavo dígito (o teclado não cresce sem limite). */
export const PIN_MAX_DIGITS = 8;

/** Quantas teclas formam um crachá — o mesmo 12 de `isLikelyBadge`. */
export const BADGE_KEYS = 12;

/** Mediana de intervalo (ms) entre teclas que ainda é MÁQUINA. Leitor HID:
 *  ~10-30ms por caractere. Digitador humano ágil: 60-120ms. O corte fica no vão
 *  entre os dois — rajada de leitor passa folgada, dedo nenhum chega perto. */
export const MACHINE_MEDIAN_MAX_MS = 40;

/** O buffer guarda só o rabo recente: cabe um crachá inteiro depois de um PIN
 *  cheio, e credencial não fica acumulando na memória da tela. */
export const CAPTURE_MAX_KEYS = 24;

export interface CapturedKey {
  /** O caractere (só [0-9a-f] entra — ver `isCaptureKey`). */
  char: string;
  /** Intervalo (ms) desde a entrada anterior; 0 na primeira do buffer. */
  gapMs: number;
  /** Se conta para o PIN visível: dígito que chegou com o pad aberto e fora de
   *  um campo de texto. Letras de crachá e teclas de outras fases ficam no
   *  buffer (para o rabo fechar um token) sem aparecer como bolinha. */
  pinEligible: boolean;
}

/** O que a captura aceita: um caractere que PODE pertencer a um crachá ou a um
 *  PIN. Todo o resto (letras não-hex, espaço, pontuação, teclas de controle)
 *  segue o caminho normal do browser. */
export function isCaptureKey(key: string): boolean {
  return key.length === 1 && /^[0-9a-f]$/i.test(key);
}

/** Acumula uma entrada no buffer. Pura de propósito: o intervalo entra como
 *  número (`gapMs`), então a regra de cadência é testável sem timer nem relógio
 *  falso — quem mede o intervalo é o chamador. */
export function captureKey(
  keys: readonly CapturedKey[],
  char: string,
  gapMs: number,
  pinEligible: boolean,
): readonly CapturedKey[] {
  if (!isCaptureKey(char)) return keys;
  const next = [
    ...keys,
    { char, gapMs, pinEligible: pinEligible && /^[0-9]$/.test(char) },
  ];
  return next.length > CAPTURE_MAX_KEYS ? next.slice(next.length - CAPTURE_MAX_KEYS) : next;
}

/** O PIN visível: os dígitos elegíveis do buffer, na ordem, até o teto. */
export function capturedPin(keys: readonly CapturedKey[]): string {
  let pin = "";
  for (const key of keys) {
    if (!key.pinEligible) continue;
    if (pin.length >= PIN_MAX_DIGITS) break;
    pin += key.char;
  }
  return pin;
}

/** Backspace do PIN: remove o último dígito elegível — e o que chegou depois
 *  dele (letras invisíveis não podem sobrar "atrás" do cursor). */
export function backspaceCapture(keys: readonly CapturedKey[]): readonly CapturedKey[] {
  for (let i = keys.length - 1; i >= 0; i -= 1) {
    if (keys[i]!.pinEligible) return keys.slice(0, i);
  }
  return keys;
}

export type EnterResolution =
  | { kind: "badge"; token: string; keys: readonly CapturedKey[] }
  | { kind: "human" };

/** A decisão do Enter: crachá ou gente.
 *
 * Crachá quando o rabo do buffer tem as `BADGE_KEYS` teclas de um token
 * (`isLikelyBadge`) E a cadência interna dessa passada foi de máquina — a
 * mediana dos intervalos entre as teclas do rabo (mais o intervalo até o Enter)
 * dentro de `MACHINE_MEDIAN_MAX_MS`. Digitação humana, por mais rápida que
 * seja, NUNCA fecha um crachá: 60ms por tecla já fica longe do corte.
 *
 * No crachá, devolve o buffer SEM o rabo consumido: dígitos do token que
 * chegaram a aparecer como bolinha somem do PIN, e o que a pessoa tinha
 * digitado antes da passada continua intacto.
 */
export function resolveEnter(
  keys: readonly CapturedKey[],
  enterGapMs: number,
): EnterResolution {
  if (keys.length < BADGE_KEYS) return { kind: "human" };
  const tail = keys.slice(keys.length - BADGE_KEYS);
  const token = tail.map((key) => key.char).join("");
  if (!isLikelyBadge(token)) return { kind: "human" };
  const gaps = [...tail.slice(1).map((key) => key.gapMs), enterGapMs];
  if (median(gaps) > MACHINE_MEDIAN_MAX_MS) return { kind: "human" };
  return { kind: "badge", token, keys: keys.slice(0, keys.length - BADGE_KEYS) };
}

function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
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
export function canSubmitPin(quem: number | string | null, pin: string): boolean {
  // `quem` era `operatorId: number`. Virou "identificador de quem", porque a
  // MESMA peça de identificação serve o operador (id numérico) e o gerente
  // (username) — e um `number` obrigava o diálogo do gerente a inventar um id
  // ou a ter um pad próprio, que foi como nasceram os componentes duplicados.
  if (quem == null) return false;
  if (typeof quem === "string" && !quem.trim()) return false;
  return pin.trim().length >= 4;
}

/** Append a digit to the PIN buffer, capped (keypads shouldn't grow unbounded). */
export function appendPinDigit(pin: string, digit: string, max = PIN_MAX_DIGITS): string {
  if (!/^[0-9]$/.test(digit)) return pin;
  return pin.length >= max ? pin : pin + digit;
}
