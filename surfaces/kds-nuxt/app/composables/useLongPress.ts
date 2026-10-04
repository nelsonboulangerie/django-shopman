// Toque longo (prévia v4 `cozinha-celular` b, nota 7: "Desfazer, reabrir e o pedido
// no toque longo, sem botões a mais na tela"). Segurar o dedo ~0,5 s sobre o ticket
// abre o menu do pedido; o toque curto continua fazendo o que fazia. Quando o toque
// longo dispara, o clique que o navegador manda ao soltar o dedo é engolido: senão o
// mesmo gesto abriria o menu E traria o ticket para o foco.

export const LONG_PRESS_MS = 500;
/** Arrastar mais que isto é rolar a lista, não segurar. */
const MOVE_TOLERANCE_PX = 10;

export function useLongPress(onLongPress: () => void, delay = LONG_PRESS_MS) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let origin: { x: number; y: number } | null = null;
  let fired = false;

  function clear() {
    if (timer) clearTimeout(timer);
    timer = null;
    origin = null;
  }

  function onPointerdown(event: PointerEvent) {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    fired = false;
    origin = { x: event.clientX, y: event.clientY };
    clear();
    origin = { x: event.clientX, y: event.clientY };
    timer = setTimeout(() => {
      timer = null;
      fired = true;
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        try {
          navigator.vibrate(30);
        } catch {
          // Sem vibração: o menu que abre já é a resposta.
        }
      }
      onLongPress();
    }, delay);
  }

  function onPointermove(event: PointerEvent) {
    if (!origin) return;
    if (Math.abs(event.clientX - origin.x) > MOVE_TOLERANCE_PX || Math.abs(event.clientY - origin.y) > MOVE_TOLERANCE_PX) {
      clear();
    }
  }

  /** Engole o clique que segue um toque longo (fase de captura). */
  function onClickCapture(event: MouseEvent) {
    if (!fired) return;
    fired = false;
    event.preventDefault();
    event.stopPropagation();
  }

  function onContextmenu(event: Event) {
    // O menu do sistema (copiar, selecionar) não serve para nada num ticket.
    event.preventDefault();
  }

  onBeforeUnmount(clear);

  return {
    onPointerdown,
    onPointermove,
    onPointerup: clear,
    onPointercancel: clear,
    onPointerleave: clear,
    onClickCapture,
    onContextmenu,
  };
}
