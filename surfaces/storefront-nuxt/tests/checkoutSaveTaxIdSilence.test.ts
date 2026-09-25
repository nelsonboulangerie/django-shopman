import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Decisão do dono (25/09/2026): nada vaza que um CPF pertence a outra conta.
// "Guardar no seu cadastro?" não tem resposta na tela: o servidor não devolve o
// desfecho, e a loja não pode voltar a ler um nem a dizer "não entrou no seu
// cadastro" (era a frase que deixava inferir a outra conta).
const root = fileURLToPath(new URL('..', import.meta.url))

function read (path: string) {
  return readFileSync(join(root, path), 'utf8')
}

describe('guardar o CPF no cadastro não tem resposta na tela', () => {
  const sources = ['app/pages/finalizar.vue', 'app/presentation/taxId.ts', 'app/types/shopman.ts']

  it.each(sources)('%s não lê o desfecho do guardar', (path) => {
    expect(read(path)).not.toMatch(/tax_id_saved/)
  })

  it.each(sources)('%s não diz que o documento ficou fora do cadastro', (path) => {
    expect(read(path)).not.toMatch(/não entrou no seu cadastro/i)
  })
})
