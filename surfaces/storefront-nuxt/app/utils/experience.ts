import type { ShellResponse } from '~/types/shopman'

/**
 * A versão padrão de todo experimento da loja (R4 do release, OC-20/OC-21).
 *
 * A `ExperienceRule` do servidor nasce com `variants: ["a", "b"]` e `default: "a"`
 * (plano da Etapa II, §7.2). Experimento ausente do shell (regra desligada, shell
 * sem o campo, shell que não carregou) é a versão padrão.
 */
export const DEFAULT_EXPERIENCE_VARIANT = 'a'

type ShellLike = Pick<ShellResponse, 'shell'> | null | undefined

/** A versão que o servidor decidiu para `ref` neste shell, ou a padrão. */
export function experienceVariant (shell: ShellLike, ref: string): string {
  const items = shell?.shell?.experience
  if (!Array.isArray(items)) return DEFAULT_EXPERIENCE_VARIANT
  const found = items.find(item => item?.ref === ref)
  const variant = typeof found?.variant === 'string' ? found.variant.trim() : ''
  return variant || DEFAULT_EXPERIENCE_VARIANT
}

/**
 * Este shell carrega alguma versão fora da padrão?
 *
 * Então o documento que o embute é de UMA pessoa (X14): nenhum cache compartilhado
 * pode guardá-lo. Conservador por construção: se um experimento algum dia tiver
 * outra padrão, o documento sai privado a mais, nunca público a mais.
 */
export function hasNonDefaultExperience (shell: ShellLike): boolean {
  const items = shell?.shell?.experience
  if (!Array.isArray(items)) return false
  return items.some(item => typeof item?.variant === 'string' && item.variant.trim() !== '' && item.variant.trim() !== DEFAULT_EXPERIENCE_VARIANT)
}

const SHARED_CACHE_DIRECTIVES = new Set(['public', 'private', 'no-store', 'no-cache', 'max-age', 's-maxage', 'stale-while-revalidate', 'stale-if-error', 'immutable', 'must-revalidate', 'proxy-revalidate'])

/**
 * O `Cache-Control` de um documento que carrega versão de experimento: `private,
 * no-store`, preservando o que não fala de guarda (o `no-transform` da home, que
 * segura a ofuscação de e-mail da Cloudflare).
 */
export function privateDocumentCacheControl (existing: unknown): string {
  const kept = String(existing ?? '')
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
    .filter(part => !SHARED_CACHE_DIRECTIVES.has(part.split('=')[0]!.trim().toLowerCase()))
  return ['private', 'no-store', ...kept].join(', ')
}
