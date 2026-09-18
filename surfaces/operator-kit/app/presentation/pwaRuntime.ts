// Decisões PURAS da troca de versão do app instalado — sem DOM, sem timer, sem rede.
// Quem as executa é `usePwaAutoUpdate`; quem as prova é `tests/pwaRuntime.test.ts`.
//
// O problema que elas resolvem (medido em 17/09/2026, PRs #783/#789): o worker novo
// fica em "waiting" até TODAS as janelas do host fecharem, e o PDV instalado no
// desktop do dono ficou dias com o bundle antigo. A resposta tem duas metades: SONDAR
// (perguntar ao servidor se há `sw.js` novo) e APLICAR sozinho num momento que a
// superfície comprove ser seguro. Nada aqui aplica nada sem as duas coisas.

/** Sonda a cada 30 min: pega o deploy do dia sem transformar o kiosk em pinger. */
export const PWA_UPDATE_CHECK_MS = 30 * 60 * 1000;

/** Piso entre sondas: foco/visibilidade/rede disparam em rajada ao voltar do sono. */
export const PWA_UPDATE_CHECK_FLOOR_MS = 60 * 1000;

/** Sem toque por este tempo, a superfície é considerada ociosa para recarregar. */
export const PWA_UPDATE_IDLE_MS = 60 * 1000;

export function idleReloadPathAllowed(allowedPaths: readonly string[], path: string): boolean {
  return allowedPaths.some((allowed) => {
    if (allowed === "*") return true;
    // `"/"` libera SÓ a raiz. Sem este corte o prefixo vira coringa (todo caminho
    // começa com "/") e `/session` do PDV — contagem de caixa aberta — recarregaria.
    const base = allowed.replace(/\/+$/, "");
    if (!base) return path === "/" || path === "";
    return path === base || path.startsWith(`${base}/`);
  });
}

/**
 * Sondar agora? Vale para os gatilhos OPORTUNISTAS — voltar à vista, ganhar foco —,
 * que chegam em rajada quando o aparelho acorda e precisam de um piso entre si. A
 * sonda do intervalo de 30 min e a da volta da rede não passam por aqui: a primeira
 * já é rara, e as duas devem acontecer justamente com a janela em segundo plano, que
 * é o estado do PDV instalado no desktop do dono.
 */
export function shouldCheckForUpdate(options: {
  now: number;
  lastCheckAt: number;
  online: boolean;
  visible: boolean;
  floorMs?: number;
}): boolean {
  if (!options.online || !options.visible) return false;
  const floor = options.floorMs ?? PWA_UPDATE_CHECK_FLOOR_MS;
  // Relógio para trás (aparelho de balcão com hora ajustada) não pode congelar a sonda.
  if (options.now < options.lastCheckAt) return true;
  return options.now - options.lastCheckAt >= floor;
}

export interface IdleUpdateState {
  idle: boolean;
  needsRefresh: boolean;
  applying: boolean;
  safeToReload: boolean;
  /** Razões NOMEADAS que a superfície publicou para não recarregar agora. */
  holds: readonly string[];
}

/**
 * O que impede a aplicação automática, na ordem em que interessa a quem lê o log.
 * `null` = nada impede. Devolver a RAZÃO, e não um booleano, é o que permite ao
 * relatório dizer "não aplicou porque havia comanda aberta" em vez de "não aplicou".
 */
export function idleUpdateBlocker(state: IdleUpdateState): string | null {
  if (!state.needsRefresh) return "no_update";
  if (state.applying) return "applying";
  if (!state.safeToReload) return "unsafe_route";
  const [firstHold] = state.holds;
  if (firstHold) return firstHold;
  if (!state.idle) return "busy";
  return null;
}

export function shouldApplyIdleUpdate(state: IdleUpdateState): boolean {
  return idleUpdateBlocker(state) === null;
}

export async function applyIdleUpdate(
  options: {
    allowedPaths: readonly string[];
    path: string;
    idle: boolean;
    needsRefresh: boolean;
    applying: boolean;
    holds?: readonly string[];
  },
  update: () => Promise<boolean>,
): Promise<boolean> {
  if (!shouldApplyIdleUpdate({
    idle: options.idle,
    needsRefresh: options.needsRefresh,
    applying: options.applying,
    safeToReload: idleReloadPathAllowed(options.allowedPaths, options.path),
    holds: options.holds || [],
  })) return false;
  return update();
}
