import type { Page } from '@playwright/test'

// O ViaCEP que o NAVEGADOR consulta ao digitar o CEP (AddressPicker.lookupCep, URL fixa no
// componente) vai aos mapas falsos da pilha (shopman/shop/tests/e2e/fake_maps.py), que o
// responde no formato dele a partir de uma tabela fixa. Nenhuma consulta sai da máquina:
// TODA URL de viacep.com.br cai nesta rota; a que não for de CEP é abortada e anotada.
const MAPS = (process.env.JOURNEY_MAPS_URL || `http://127.0.0.1:${process.env.JOURNEYS_MAPS_PORT || '12192'}`).replace(/\/$/, '')

export interface ViaCepLog {
  /** Cada CEP que o navegador consultou, servido pelo fake. */
  served: string[]
  /** URLs de viacep.com.br que não eram consulta de CEP: abortadas, nunca chegaram lá. */
  refused: string[]
}

export async function viaCepFromFakeMaps (page: Page): Promise<ViaCepLog> {
  const log: ViaCepLog = { served: [], refused: [] }
  await page.context().route(/^https?:\/\/viacep\.com\.br\//, async (route) => {
    const url = route.request().url()
    const cep = url.match(/^https?:\/\/viacep\.com\.br\/ws\/(\d{8})\/json\/?$/)?.[1]
    if (!cep) {
      log.refused.push(url)
      await route.abort()
      return
    }
    const response = await route.fetch({ url: `${MAPS}/ws/${cep}/json/` })
    log.served.push(cep)
    await route.fulfill({ response })
  })
  return log
}
