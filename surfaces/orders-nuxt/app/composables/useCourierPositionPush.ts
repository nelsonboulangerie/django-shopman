// A posição do entregador chega pelo SSE (`backstage-courier-position`, F7b): no máximo
// um aviso a cada 10 s por corrida, do servidor. Com várias corridas na rua, a página
// receberia um aviso por corrida; aqui os avisos viram UMA releitura a cada 10 s, a
// primeira na hora e a que chegou no meio no fim da janela (nenhuma posição se perde).
export const COURIER_POSITION_REFRESH_MS = 10_000;

export function courierPositionThrottle(refresh: () => void, windowMs = COURIER_POSITION_REFRESH_MS) {
  let last = Number.NEGATIVE_INFINITY;
  let timer: ReturnType<typeof setTimeout> | null = null;
  function run() {
    timer = null;
    last = Date.now();
    refresh();
  }
  return {
    push() {
      if (timer) return;
      const wait = last + windowMs - Date.now();
      if (wait <= 0) run();
      else timer = setTimeout(run, wait);
    },
    stop() {
      if (timer) clearTimeout(timer);
      timer = null;
    },
  };
}

export function useCourierPositionPush(refresh: () => void) {
  const throttle = courierPositionThrottle(refresh);
  onBeforeUnmount(throttle.stop);
  return throttle.push;
}
