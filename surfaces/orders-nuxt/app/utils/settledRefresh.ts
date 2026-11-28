// A leitura puxada por PUSH (SSE, reabrir do stream, voltar à aba) espera a rajada
// assentar e lê UMA vez. Uma ação no detalhe gera o evento dela, o do ticket da
// Cozinha e às vezes o reabrir do stream: cada um relia o pedido, e o beta de 05/11
// (GES-17) mediu 3 GET seguidos por ação. A releitura da própria ação continua
// imediata (`refresh` do useOrderDetail); só o eco do push espera a janela.
export interface SettledRefresh {
  (): void;
  cancel(): void;
}

export function settledRefresh(
  read: () => unknown,
  windowMs = 800,
): SettledRefresh {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const trigger = (() => {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      // Leitura que falha não derruba o push: a próxima (poll, visibilidade) refaz.
      void Promise.resolve()
        .then(read)
        .catch(() => {});
    }, windowMs);
  }) as SettledRefresh;
  trigger.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  return trigger;
}
