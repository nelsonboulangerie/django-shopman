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
