// O leitor de código (modo teclado) numa tela de operador: o ouvinte na fase de
// CAPTURA da janela, o timer de silêncio e a devolução das teclas retidas ao
// campo onde elas iam cair. A regra (o que é rajada de leitor, o que é dedo) é
// pura e mora em `presentation/codeScan`; o que fazer com o código é de quem usa.
//
// Mesma técnica do leitor da Via Cozinha no PDV (`useKitchenTicketScanner`).
import { onBeforeUnmount, onMounted } from "vue";

import {
  EMPTY_SCAN,
  SCAN_KEY_GAP_MAX_MS,
  scanKey,
  scanTimeout,
  type CodeFormat,
  type ScanState,
} from "../presentation/codeScan";

type Target = HTMLElement | null;

function isEditable(el: Target): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement) return !el.readOnly && !el.disabled;
  if (el instanceof HTMLInputElement) {
    const textual = ["text", "search", "tel", "email", "url", "password", "number", ""].includes(el.type);
    return textual && !el.readOnly && !el.disabled;
  }
  return el.isContentEditable;
}

const replayed = new WeakSet<Event>();

/** Devolve ao campo as teclas que ficaram retidas, onde está o cursor. */
function giveBack(target: Target, text: string): void {
  if (!text || !target) return;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
    if (!isEditable(target)) return;
    try {
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? start;
      target.setRangeText(text, start, end, "end");
    } catch {
      target.value += text;
    }
    target.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  if (target.isContentEditable) {
    document.execCommand("insertText", false, text);
    return;
  }
  for (const char of text) {
    const replay = new KeyboardEvent("keydown", { key: char, bubbles: true, cancelable: true });
    replayed.add(replay);
    target.dispatchEvent(replay);
  }
}

export function useCodeScanner(options: {
  format: CodeFormat;
  /** Só escuta quando a tela pode agir (identificada, destravada). */
  enabled: () => boolean;
  /** O leitor fechou um código no formato. */
  onCode: (code: string) => void | Promise<void>;
  /** O leitor fechou uma rajada com o prefixo, fora do formato. */
  onInvalid?: (text: string) => void;
}) {
  let state: ScanState = EMPTY_SCAN;
  let lastAt = 0;
  let heldTarget: Target = null;
  let silence: ReturnType<typeof setTimeout> | null = null;

  function clearSilence() {
    if (silence) clearTimeout(silence);
    silence = null;
  }

  function reset() {
    clearSilence();
    state = EMPTY_SCAN;
    lastAt = 0;
    heldTarget = null;
  }

  function armSilence() {
    clearSilence();
    silence = setTimeout(() => {
      const target = heldTarget;
      const { release } = scanTimeout(options.format, state);
      reset();
      giveBack(target, release);
    }, SCAN_KEY_GAP_MAX_MS + 10);
  }

  function onKeydown(event: KeyboardEvent) {
    if (replayed.has(event) || !options.enabled()) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const now = Date.now();
    const gap = state.buffer ? now - lastAt : Number.POSITIVE_INFINITY;
    const target = (event.target as HTMLElement | null) ?? null;
    const { state: next, step } = scanKey(options.format, state, event.key, gap);

    switch (step.kind) {
      case "pass":
        return;
      case "hold":
        if (!state.buffer) heldTarget = target;
        state = next;
        lastAt = now;
        event.preventDefault();
        event.stopPropagation();
        armSilence();
        return;
      case "release": {
        const back = heldTarget;
        reset();
        giveBack(back, step.text);
        return;
      }
      case "code":
        reset();
        event.preventDefault();
        event.stopPropagation();
        void options.onCode(step.code);
        return;
      case "invalid":
        reset();
        event.preventDefault();
        event.stopPropagation();
        options.onInvalid?.(step.text);
    }
  }

  onMounted(() => window.addEventListener("keydown", onKeydown, true));
  onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown, true);
    reset();
  });
}
