// O leitor de código da bancada, em qualquer tela do PDV.
//
// A regra (o que é rajada de leitor, o que é dedo) é pura e mora em
// `presentation/ticketScan`. Aqui mora o que é do navegador: o ouvinte de
// teclado na fase de CAPTURA da janela (antes de qualquer campo ou atalho da
// tela), o timer de silêncio, a devolução das teclas retidas ao campo onde
// elas iam cair, e a chamada ao servidor com o aviso e o som.
//
// Por que devolver e não só deixar passar: a primeira tecla de uma rajada não
// se distingue olhando para trás (não há nada antes dela). O "K" é retido até
// a segunda tecla — ou o silêncio — dizer o que ele era. Se era dedo, ele volta
// ao campo exatamente onde estava o cursor, antes da tecla seguinte.
import { onBeforeUnmount, onMounted } from "vue";

import {
  EMPTY_SCAN,
  SCAN_KEY_GAP_MAX_MS,
  scanKey,
  scanTimeout,
  type ScanState,
} from "~/presentation/ticketScan";
import type { POSKitchenTicketReceipt } from "~/types/pos";

/** A figura do "pronto": duas notas subindo, curtas — a casa comemorando, sem
 *  a fanfarra do KDS (quem lê o papel está no balcão, não na cozinha). */
const READY_NOTES = [
  { f: 783.99, t: 0, d: 0.35 },
  { f: 1174.66, t: 0.1, d: 0.6 },
];
/** Algo deu errado: uma nota só, grave. */
const REFUSED_NOTES = [{ f: 311.13, t: 0, d: 0.5 }];

type Target = HTMLElement | null;

function isEditable(el: Target): el is HTMLInputElement | HTMLTextAreaElement | HTMLElement {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement) return !el.readOnly && !el.disabled;
  if (el instanceof HTMLInputElement) {
    const textual = ["text", "search", "tel", "email", "url", "password", "number", ""].includes(el.type);
    return textual && !el.readOnly && !el.disabled;
  }
  return el.isContentEditable;
}

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
      // `type=number` não tem seleção: acrescenta no fim.
      target.value += text;
    }
    target.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  if (target.isContentEditable) {
    // `execCommand` é o único jeito de inserir com undo num contenteditable.
    document.execCommand("insertText", false, text);
    return;
  }
  // Fora de campo, as teclas iam para atalhos da tela: devolvidas como eventos,
  // marcados para este ouvinte não retê-las de novo.
  for (const char of text) {
    const replay = new KeyboardEvent("keydown", { key: char, bubbles: true, cancelable: true });
    replayed.add(replay);
    target.dispatchEvent(replay);
  }
}

const replayed = new WeakSet<Event>();

export function useKitchenTicketScanner(options: {
  /** Só escuta com alguém identificado e a tela destravada. */
  enabled: () => boolean;
}) {
  const { call } = usePosAction();
  const { beep: beepReady } = useAlertSound("pos_ticket_scan_sound", { notes: READY_NOTES });
  const { beep: beepRefused } = useAlertSound("pos_ticket_scan_sound", { notes: REFUSED_NOTES });

  let state: ScanState = EMPTY_SCAN;
  let lastAt = 0;
  let heldTarget: Target = null;
  let silence: ReturnType<typeof setTimeout> | null = null;
  const busy = new Set<string>();

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
      const { release } = scanTimeout(state);
      reset();
      giveBack(target, release);
    }, SCAN_KEY_GAP_MAX_MS + 10);
  }

  async function complete(code: string) {
    if (busy.has(code)) return;
    busy.add(code);
    try {
      const response = await call<{ ticket: POSKitchenTicketReceipt }>("/api/v1/backstage/kds/printed-tickets/scan/", {
        method: "POST",
        body: { code },
      });
      const receipt = response.ticket;
      if (receipt.completed_now) {
        useSonner.success(receipt.message);
        beepReady();
      } else {
        useSonner.info(receipt.message);
      }
    } catch (error) {
      useSonner.error(httpErrorMessage(error, "Não deu para dar o pronto por este código. Tente de novo."));
      beepRefused();
    } finally {
      busy.delete(code);
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (replayed.has(event) || !options.enabled()) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const now = Date.now();
    const gap = state.buffer ? now - lastAt : Number.POSITIVE_INFINITY;
    const target = (event.target as HTMLElement | null) ?? null;
    const { state: next, step } = scanKey(state, event.key, gap);

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
        return; // a tecla atual segue o caminho normal, depois das devolvidas
      }
      case "code":
        reset();
        event.preventDefault(); // o Enter do leitor não clica no botão focado
        event.stopPropagation();
        void complete(step.code);
        return;
      case "invalid":
        reset();
        event.preventDefault();
        event.stopPropagation();
        useSonner.error("Código não reconhecido: não é de uma Via Cozinha desta loja.");
        beepRefused();
    }
  }

  onMounted(() => window.addEventListener("keydown", onKeydown, true));
  onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown, true);
    reset();
  });

  return { complete };
}
