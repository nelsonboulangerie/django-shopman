// Registro do INSTANTE em que o app instalado trocou de versão.
//
// A troca termina num `location.reload()`: nada que fique só na memória sobrevive
// para contar o que aconteceu. Então a marca é escrita ANTES do reload e enviada no
// boot seguinte, quando o bundle novo já está rodando — é isso que transforma
// "parece que ainda é a versão antiga" numa linha de log com as duas versões.
//
// Silencioso por construção, como o `reportClientError`: telemetria nunca vira erro
// na frente do operador, e `localStorage` ausente (janela anônima, armazenamento
// bloqueado) só significa uma prova a menos, nunca uma atualização a menos.

export const PWA_UPDATE_STORAGE_KEY = "shopman:operator:pwa-update";
export const PWA_UPDATE_ENDPOINT = "/api/v1/backstage/client-pwa-update/";

/** O gatilho da troca: o operador aceitou o aviso, ou a superfície aplicou sozinha. */
export type PwaUpdateTrigger = "prompt" | "idle";

export interface PwaUpdateMark {
  app: string;
  trigger: PwaUpdateTrigger;
  /** Versão que estava rodando quando a troca foi disparada. */
  from_version: string;
}

export interface PwaUpdateReport extends PwaUpdateMark {
  /** Versão que está rodando AGORA, no boot que envia o relatório. */
  to_version: string;
}

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

/** Grava a marca. Chamada imediatamente antes de `updateServiceWorker(true)`. */
export function markPwaUpdateApplied(mark: PwaUpdateMark): boolean {
  try {
    storage()?.setItem(PWA_UPDATE_STORAGE_KEY, JSON.stringify(mark));
    return true;
  } catch {
    return false;
  }
}

/**
 * Lê e APAGA a marca. Apagar antes de enviar é deliberado: uma falha de rede no
 * relato não pode fazer o app repetir o mesmo relato a cada boot para sempre.
 */
export function takePwaUpdateMark(): PwaUpdateMark | null {
  const store = storage();
  if (!store) return null;
  let raw: string | null;
  try {
    raw = store.getItem(PWA_UPDATE_STORAGE_KEY);
    store.removeItem(PWA_UPDATE_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PwaUpdateMark>;
    if (typeof parsed?.app !== "string" || !parsed.app) return null;
    if (parsed.trigger !== "prompt" && parsed.trigger !== "idle") return null;
    return {
      app: parsed.app,
      trigger: parsed.trigger,
      from_version: typeof parsed.from_version === "string" ? parsed.from_version : "",
    };
  } catch {
    return null;
  }
}

/**
 * Envia a marca pendente pelo BFF. Devolve o que foi relatado (para o teste e para
 * quem quiser mostrar), ou `null` quando não havia troca a relatar.
 */
/**
 * O POST, isolado numa função própria: o caminho fica literal (a inferência de rota do
 * `$fetch` precisa dele) e o resultado morre aqui, sem virar tipo de retorno — devolver
 * a promessa do `$fetch` estoura a profundidade de tipo do TypeScript.
 */
async function postPwaUpdate(body: PwaUpdateReport): Promise<void> {
  await $fetch(PWA_UPDATE_ENDPOINT, { method: "POST", body });
}

export async function reportPwaUpdateApplied(
  toVersion: string,
  post: (body: PwaUpdateReport) => Promise<unknown> = postPwaUpdate,
): Promise<PwaUpdateReport | null> {
  const mark = takePwaUpdateMark();
  if (!mark) return null;
  const report: PwaUpdateReport = { ...mark, to_version: toVersion };
  try {
    await post(report);
  } catch {
    // Já apagada: o relato se perde, a atualização não.
  }
  return report;
}
