// Registro do INSTANTE em que a loja instalada trocou de versão (#2379).
//
// Porte do `operator-kit/app/utils/pwaUpdateReport.ts`. A troca termina numa carga nova
// da página: nada que fique só na memória sobrevive para contar o que aconteceu. Então
// a marca é escrita ANTES da troca e enviada no boot seguinte, quando o bundle novo já
// está rodando: é isso que transforma "parece que a loja ainda é a versão antiga" numa
// linha de log com as duas versões (evento `pwa.update_applied`, `app="storefront"`).
//
// Silencioso por construção, como o relato de erro: telemetria nunca aparece para a
// cliente, e `localStorage` ausente (janela anônima, armazenamento bloqueado) só
// significa uma prova a menos, nunca uma atualização a menos.

export const PWA_UPDATE_STORAGE_KEY = 'shopman:storefront:pwa-update'
export const PWA_UPDATE_ENDPOINT = '/api/v1/storefront/client-pwa-update/'

/** O gatilho: o toque em "Atualizar", ou a troca de tela que aplicou a versão nova. */
export type PwaUpdateTrigger = 'prompt' | 'navigation'

export interface PwaUpdateMark {
  trigger: PwaUpdateTrigger
  /** Versão que estava rodando quando a troca foi disparada. */
  from_version: string
}

export interface PwaUpdateReport extends PwaUpdateMark {
  /** Versão que está rodando AGORA, no boot que envia o relato. */
  to_version: string
}

function storage (): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

/** Grava a marca. Chamada imediatamente antes de `updateServiceWorker(true)`. */
export function markPwaUpdateApplied (mark: PwaUpdateMark): boolean {
  try {
    storage()?.setItem(PWA_UPDATE_STORAGE_KEY, JSON.stringify(mark))
    return true
  } catch {
    return false
  }
}

/**
 * Lê e APAGA a marca. Apagar antes de enviar é deliberado: uma falha de rede no relato
 * não pode fazer a loja repetir o mesmo relato a cada boot para sempre.
 */
export function takePwaUpdateMark (): PwaUpdateMark | null {
  const store = storage()
  if (!store) return null
  let raw: string | null
  try {
    raw = store.getItem(PWA_UPDATE_STORAGE_KEY)
    store.removeItem(PWA_UPDATE_STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<PwaUpdateMark>
    if (parsed?.trigger !== 'prompt' && parsed?.trigger !== 'navigation') return null
    return {
      trigger: parsed.trigger,
      from_version: typeof parsed.from_version === 'string' ? parsed.from_version : ''
    }
  } catch {
    return null
  }
}

/**
 * Envia a marca pendente. Devolve o que foi relatado (para o teste), ou `null` quando
 * não havia troca a relatar.
 */
export async function reportPwaUpdateApplied (
  toVersion: string,
  post: (body: PwaUpdateReport) => Promise<unknown>
): Promise<PwaUpdateReport | null> {
  const mark = takePwaUpdateMark()
  if (!mark) return null
  const report: PwaUpdateReport = { ...mark, to_version: toVersion }
  try {
    await post(report)
  } catch {
    // Já apagada: o relato se perde, a atualização não.
  }
  return report
}
