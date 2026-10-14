// Presentation — o leitor de código (modo teclado, HID) em qualquer tela de operador.
//
// O leitor "digita" o código depressa e fecha com Enter. A tela reconhece a
// rajada pelo PREFIXO do código e pela cadência de máquina, e ela não cai no
// campo que está com o foco. A regra é a do leitor da Via Cozinha no PDV
// (`pos-nuxt/app/presentation/ticketScan.ts`), aqui com o prefixo e o formato
// como parâmetro: toda tecla que PODE ser o começo de um código fica retida; se
// o que vem depois não é rajada de leitor (um dedo digitou a letra num nome),
// as teclas retidas são DEVOLVIDAS ao campo, na ordem. Quem digita não perde
// letra; o leitor não suja campo nenhum.
//
// Puro de propósito: o intervalo entre teclas entra como número; o timer de
// silêncio e a devolução ao campo são do composable (`useCodeScanner`).

import { MACHINE_MEDIAN_MAX_MS } from "./operatorLock";

/** Intervalo máximo (ms) entre duas teclas da MESMA rajada (ver `ticketScan`). */
export const SCAN_KEY_GAP_MAX_MS = MACHINE_MEDIAN_MAX_MS * 2;

export interface CodeFormat {
  /** O começo de todo código deste tipo, em maiúsculas (ex.: "VP-"). */
  prefix: string;
  /** O código inteiro, em maiúsculas. */
  pattern: RegExp;
  /** Teto de uma rajada: mais que isso não é código nosso. */
  maxLength: number;
}

export interface ScanState {
  /** O que a rajada em curso já trouxe (vazio = nada retido). */
  buffer: string;
}

export const EMPTY_SCAN: ScanState = { buffer: "" };

export type ScanStep =
  | { kind: "pass" }
  | { kind: "hold" }
  | { kind: "release"; text: string }
  | { kind: "code"; code: string }
  | { kind: "invalid"; text: string };

/** O que fazer com uma tecla. `gapMs` = tempo desde a tecla anterior RETIDA
 *  (Infinity quando não há nada retido). */
export function scanKey(
  format: CodeFormat,
  state: ScanState,
  key: string,
  gapMs: number,
): { state: ScanState; step: ScanStep } {
  const buffer = state.buffer;
  if (key.length !== 1 && key !== "Enter") return { state, step: { kind: "pass" } };

  if (!buffer) {
    if (key.toUpperCase() === format.prefix[0]) return { state: { buffer: key }, step: { kind: "hold" } };
    return { state, step: { kind: "pass" } };
  }

  if (gapMs > SCAN_KEY_GAP_MAX_MS) return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };

  const prefixDone = buffer.toUpperCase().startsWith(format.prefix);

  if (key === "Enter") {
    if (!prefixDone) return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };
    const code = buffer.toUpperCase().trim();
    if (format.pattern.test(code)) return { state: EMPTY_SCAN, step: { kind: "code", code } };
    return { state: EMPTY_SCAN, step: { kind: "invalid", text: buffer } };
  }

  if (!prefixDone) {
    const next = (buffer + key).toUpperCase();
    if (format.prefix.startsWith(next)) return { state: { buffer: buffer + key }, step: { kind: "hold" } };
    return { state: EMPTY_SCAN, step: { kind: "release", text: buffer } };
  }

  if (buffer.length + 1 > format.maxLength) {
    return { state: EMPTY_SCAN, step: { kind: "invalid", text: buffer + key } };
  }
  return { state: { buffer: buffer + key }, step: { kind: "hold" } };
}

/** O silêncio fechou a janela sem Enter: o retido volta ao campo (dedo), ou é
 *  descartado quando já era leitura (prefixo completo). */
export function scanTimeout(format: CodeFormat, state: ScanState): { state: ScanState; release: string } {
  if (!state.buffer) return { state, release: "" };
  const prefixDone = state.buffer.toUpperCase().startsWith(format.prefix);
  return { state: EMPTY_SCAN, release: prefixDone ? "" : state.buffer };
}
