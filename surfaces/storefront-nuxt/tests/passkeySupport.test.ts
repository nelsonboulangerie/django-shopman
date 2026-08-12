// Onde o convite de passkey pode aparecer — e onde ele NÃO pode.
//
// ⚠️ Este arquivo existe por causa de um achado na tela: WebAuthn exige DOMÍNIO REGISTRÁVEL, e
// o Chrome recusa endereço IP com `SecurityError: This is an invalid domain`. O dev deste
// projeto roda em `127.0.0.1` por convenção, então a tela oferecia um botão que o navegador ia
// negar — e botão que falha ensina a não confiar no botão.
import { beforeEach, describe, expect, it } from 'vitest'

function pretendHost(hostname: string, { withApi = true } = {}) {
  Object.defineProperty(globalThis, 'window', {
    value: {
      location: { hostname },
      ...(withApi ? { PublicKeyCredential: function () {} } : {})
    },
    writable: true,
    configurable: true
  })
  Object.defineProperty(globalThis, 'navigator', {
    value: withApi ? { credentials: { create: () => {}, get: () => {} } } : {},
    writable: true,
    configurable: true
  })
}

describe('onde passkey pode ser oferecido', () => {
  beforeEach(() => {
    // Cada teste declara o seu ambiente; sem isto um teste herda a janela do anterior.
    delete (globalThis as { window?: unknown }).window
  })

  it('num domínio de verdade, sim', async () => {
    pretendHost('nelsonboulangerie.com.br')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(true)
  })

  it('em subdomínio de staging também', async () => {
    pretendHost('staging.nelsonboulangerie.com.br')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(true)
  })

  it('em localhost sim — é o caso especial que o WebAuthn abre', async () => {
    pretendHost('localhost')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(true)
  })

  it('⚠️ em 127.0.0.1 NÃO — e é o endereço do nosso dev', async () => {
    pretendHost('127.0.0.1')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(false)
  })

  it('em qualquer IPv4 não', async () => {
    pretendHost('192.168.0.14')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(false)
  })

  it('em IPv6 não', async () => {
    pretendHost('[::1]')
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(false)
  })

  it('sem a API do navegador não, mesmo em domínio bom', async () => {
    pretendHost('nelsonboulangerie.com.br', { withApi: false })
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(false)
  })

  it('no servidor (sem window) não — e sem explodir', async () => {
    const { passkeySupported } = await import('../app/composables/usePasskey')

    expect(passkeySupported()).toBe(false)
  })
})

describe('quando não dá, a tela DIZ — não some', () => {
  beforeEach(() => {
    delete (globalThis as { window?: unknown }).window
  })

  it('⚠️ o motivo existe, porque silêncio é a única resposta que não dá para depurar', async () => {
    // Nasceu de um relato de uma palavra: "não vi nada aqui". A seção se escondia em quatro
    // condições diferentes, cada uma certa sozinha, e juntas produziam uma tela vazia sem
    // explicação — impossível distinguir bug, falta de deploy e limitação do aparelho.
    pretendHost('127.0.0.1')
    const { passkeyBlockedReason } = await import('../app/composables/usePasskey')

    expect(passkeyBlockedReason()).toContain('endereço não permite')
  })

  it('navegador sem a API tem motivo próprio', async () => {
    pretendHost('nelsonboulangerie.com.br', { withApi: false })
    const { passkeyBlockedReason } = await import('../app/composables/usePasskey')

    expect(passkeyBlockedReason()).toContain('navegador')
  })

  it('quando dá, não há motivo nenhum a mostrar', async () => {
    pretendHost('nelsonboulangerie.com.br')
    const { passkeyBlockedReason } = await import('../app/composables/usePasskey')

    expect(passkeyBlockedReason()).toBe('')
  })

  it('no servidor não inventa motivo — a decisão espera o cliente', async () => {
    const { passkeyBlockedReason } = await import('../app/composables/usePasskey')

    expect(passkeyBlockedReason()).toBe('')
  })
})
