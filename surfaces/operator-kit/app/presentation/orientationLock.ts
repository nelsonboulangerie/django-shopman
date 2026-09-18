// Regra pura da trava de giro (Screen Orientation API) — sem I/O, sem DOM.
//
// A trava é por APARELHO: o operador escolhe travar na orientação em que o tablet
// está, e a escolha volta a valer quando o app instalado reabre. A família
// (`portrait`/`landscape`) é o que se trava, não o lado exato (`-primary`/
// `-secondary`): um tablet virado de ponta-cabeça no suporte continua legível.

export type OrientationFamily = "portrait" | "landscape";

/** Estado visível da trava: travada, livre, ou recusada pelo aparelho/contexto. */
export type OrientationLockStatus = "unlocked" | "locked" | "unsupported" | "needs-install";

export const ORIENTATION_LOCK_STORAGE_KEY = "shopman-operator-orientation-lock";

export const ORIENTATION_LOCK_COPY = {
  unsupported: "Este dispositivo não deixa o app travar o giro — use o bloqueio de rotação do sistema.",
  needsInstall: "O giro só trava com o app instalado — abra pelo ícone na tela inicial.",
  unlocked: "Giro liberado.",
} as const;

export function orientationLockedCopy(family: OrientationFamily): string {
  return family === "portrait" ? "Giro travado em retrato." : "Giro travado em paisagem.";
}

/** `landscape-primary` → `landscape`. Tipo ausente/desconhecido → null. */
export function orientationFamily(type: string | null | undefined): OrientationFamily | null {
  if (!type) return null;
  if (type.startsWith("portrait")) return "portrait";
  if (type.startsWith("landscape")) return "landscape";
  return null;
}

/** Valor persistido higienizado: só uma família válida sobrevive. */
export function parseStoredOrientation(value: unknown): OrientationFamily | null {
  return value === "portrait" || value === "landscape" ? value : null;
}

/**
 * Por que a trava falhou, dito ao operador. O navegador recusa com nomes que não
 * distinguem "nunca vai dar" de "só dá instalado" (Chrome Android numa aba comum e
 * Chrome no Windows respondem ambos `NotSupportedError`), então a leitura é pelo
 * contexto: fora do app instalado a saída é instalar; dentro dele, o aparelho não
 * permite e o bloqueio do sistema é o caminho. iPhone/iPad não deixam app web travar
 * o giro nem instalado — mandar instalar ali seria prometer o que não acontece.
 */
export function orientationLockFailure(context: { installed: boolean; ios: boolean }): Extract<OrientationLockStatus, "unsupported" | "needs-install"> {
  return context.installed || context.ios ? "unsupported" : "needs-install";
}

export function orientationFailureCopy(status: Extract<OrientationLockStatus, "unsupported" | "needs-install">): string {
  return status === "needs-install" ? ORIENTATION_LOCK_COPY.needsInstall : ORIENTATION_LOCK_COPY.unsupported;
}
