import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('..', import.meta.url))

function read (path: string) {
  return readFileSync(join(root, path), 'utf8')
}

describe('storefront localization guardrails', () => {
  it('keeps base UI fallback labels in pt-BR', () => {
    expect(read('app/components/Ui/AlertDialog/Cancel.vue')).toContain('text: "Cancelar"')
    expect(read('app/components/Ui/AlertDialog/Action.vue')).toContain('text: "Continuar"')
    expect(read('app/components/Ui/Popover/X.vue')).toContain('srText: "Fechar"')
    expect(read('app/components/Ui/Sheet/X.vue')).toContain('srText: "Fechar"')
    expect(read('app/components/Ui/Dialog/Content.vue')).toContain('<span class="sr-only">Fechar</span>')
    expect(read('app/components/Ui/Command/Dialog.vue')).toContain('title: "Paleta de comandos"')
    expect(read('app/components/Ui/Command/Dialog.vue')).toContain('description: "Busque um comando para executar..."')

    const joined = [
      'app/components/Ui/AlertDialog/Cancel.vue',
      'app/components/Ui/AlertDialog/Action.vue',
      'app/components/Ui/Popover/X.vue',
      'app/components/Ui/Sheet/X.vue',
      'app/components/Ui/Dialog/Content.vue',
      'app/components/Ui/Command/Dialog.vue'
    ].map(read).join('\n')
    expect(joined).not.toMatch(/"Cancel"|"Continue"|"Close"|"Command Palette"|"Search for a command to run\.\.\."/)
  })
})
