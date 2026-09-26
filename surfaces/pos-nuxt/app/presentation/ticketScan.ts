// Presentation — o leitor de código da bancada, lido em qualquer tela do PDV.
//
// A Via Cozinha (o papel da estação sem tela) termina num QR com o código do
// ticket, `KT-<pk>-<assinatura>`. O leitor ligado ao PC do balcão é um TECLADO
// (HID): ele "digita" o código depressa e fecha com Enter. O balcão reconhece a
// rajada e dá o pronto do ticket (decisão do dono, 26/09/2026).
//
// O difícil é a rajada não cair no campo que está com o foco (a busca de
// produto, o nome do cliente). A regra é a mesma do crachá
// (`operator-kit/presentation/operatorLock` — cadência de MÁQUINA, não de
// dedo), com uma diferença que esta tela exige: o PDV não é modal, então nada
// pode ser engolido de vez. Toda tecla que PODE ser o começo de um código
// (`K`, `T`, `-`) fica retida; se o que vem depois não é rajada de leitor — um
// dedo digitou "K" num nome —, as teclas retidas são DEVOLVIDAS ao campo, na
// ordem, antes da tecla seguinte. Quem digita não perde letra; o leitor não
// suja campo nenhum.
//
// Puro de propósito: o intervalo entre teclas entra como número, e o timer de
// silêncio e a devolução ao campo são do composable (`useKitchenTicketScanner`).

import { MACHINE_MEDIAN_MAX_MS } from "../../../operator-kit/app/presentation/operatorLock";

/** O começo de todo código de Via Cozinha. */
export const TICKET_CODE_PREFIX = "KT-";

/** O código inteiro — o mesmo formato que o servidor assina
 *  (`kitchen_ticket_print.ticket_code`). */
export const TICKET_CODE_PATTERN = /^KT-\d{1,12}-[A-Z2-7]{10}$/;

/** Intervalo máximo (ms) entre duas teclas da MESMA rajada: o dobro da
 *  mediana de máquina do crachá (`MACHINE_MEDIAN_MAX_MS`). Lá a régua é a
 *  mediana da passada inteira, que absorve um soluço do USB; aqui a decisão é
 *  tecla a tecla, então a folga precisa estar no próprio corte. Errar para
 *  mais custa pouco: o dedo que digitou "K" e parou recebe a letra de volta
 *  depois deste silêncio, e para enganar a régua ele teria de digitar um
 *  código assinado inteiro. */
export const SCAN_KEY_GAP_MAX_MS = MACHINE_MEDIAN_MAX_MS * 2;

/** Teto de uma rajada: um código tem até 26 caracteres. Mais que isso não é
 *  código nosso — é outra coisa sendo lida (código de barras longo). */
export const SCAN_MAX_LENGTH = 32;

export interface ScanState {
  /** O que a rajada em curso já trouxe (vazio = nada retido). */
  buffer: string;
}

export const EMPTY_SCAN: ScanState = { buffer: "" };

export type ScanStep =
  /** Não é nosso: a tecla segue o caminho normal. */
  | { kind: "pass" }
  /** Tecla retida (pode ser código); não vai ao campo por enquanto. */
  | { kind: "hold" }
  /** Não era código: devolva `text` ao campo e deixe a tecla atual seguir. */
  | { kind: "release"; text: string }
  /** Enter fechou um código válido — conclua o ticket. Consuma o Enter. */
  | { kind: "code"; code: string }
  /** Enter fechou uma rajada que começou como código e não é um — avise.
   *  Consuma o Enter (era do leitor, não de gente). */
  | { kind: "invalid"; text: string };

function isPrintable(key: string): boolean {
  return key.length === 1;
}

/** O que fazer com uma tecla. `gapMs` = tempo desde a tecla anterior RETIDA
 *  (Infinity quando não há nada retido). */
export function scanKey(
  state: ScanState,
  key: string,
  gapMs: number,
): { state: ScanState; step: ScanStep } {
  const buffer = state.buffer;

  // Tecla de controle (Shift que o leitor aperta para a maiúscula, setas…):
  // não muda nada. O Enter é o único controle que importa, e só com rajada.
  if (!isPrintable(key) && key !== "Enter") return { state, step: { kind: "pass" } };

  if (!buffer) {
    if (key.toUpperCase() === TICKET_CODE_PREFIX[0]) return { state: { buffer: key }, step: { kind: "hold" } };
    return { state, step: { kind: "pass" } };
  }

  // Silêncio longo demais no meio: era dedo. Devolve o retido; a tecla atual
  // segue o caminho normal (e não inicia outra retenção — o próximo "K" de
  // uma palavra não merece segurar a digitação de novo).
  if (gapMs > SCAN_KEY_GAP_MAX_MS) return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };

  const upper = buffer.toUpperCase();
  const prefixDone = upper.startsWith(TICKET_CODE_PREFIX);

  if (key === "Enter") {
    if (!prefixDone) return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };
    const code = upper.trim();
    if (TICKET_CODE_PATTERN.test(code)) return { state: EMPTY_SCAN, step: { kind: "code", code } };
    return { state: EMPTY_SCAN, step: { kind: "invalid", text: buffer } };
  }

  if (!prefixDone) {
    const next = (buffer + key).toUpperCase();
    if (TICKET_CODE_PREFIX.startsWith(next)) return { state: { buffer: buffer + key }, step: { kind: "hold" } };
    return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };
  }

  // Prefixo completo em cadência de máquina: é o leitor. Tudo até o Enter é dele.
  if (buffer.length + 1 > SCAN_MAX_LENGTH) return { state: EMPTY_SCAN, step: { kind: "invalid", text: buffer + key } };
  return { state: { buffer: buffer + key }, step: { kind: "hold" } };
}

/** O silêncio fechou a janela sem Enter: o que estava retido volta ao campo
 *  (dedo que digitou "K" e parou), ou é descartado quando já era leitura
 *  (prefixo completo — o leitor mandou lixo sem Enter; melhor calar do que
 *  despejar "KT-12" num campo). */
export function scanTimeout(state: ScanState): { state: ScanState; release: string } {
  if (!state.buffer) return { state, release: "" };
  const prefixDone = state.buffer.toUpperCase().startsWith(TICKET_CODE_PREFIX);
  return { state: EMPTY_SCAN, release: prefixDone ? "" : state.buffer };
}
