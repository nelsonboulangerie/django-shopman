import type { ComputedRef } from 'vue'
import type { ShellResponse } from '~/types/shopman'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import { experienceVariant } from '~/utils/experience'

/**
 * Qual versão da loja esta pessoa vê de um experimento (R4 do release, OC-21).
 *
 * QUEM DECIDE É O SERVIDOR (decisão D1 do dono, 23/11/2026), pela coorte configurada
 * no Admin (`RuleConfig` com `ExperienceRule`, `shopman/shop/services/experience.py`).
 * A versão chega no `shell` (`experience: [{ref, variant}]`) e este composable só a
 * LÊ do estado que o `app.vue` já buscou: não guarda estado próprio, não lê query,
 * cookie, `localStorage` nem cabeçalho, e não oferece jeito nenhum de trocar a versão.
 * Para comparar A e B lado a lado, o dono usa duas contas, uma em cada coorte.
 *
 * Experimento ausente do shell é a versão padrão `"a"` (regra desligada, kill
 * switch, prazo vencido no servidor ou shell que não carregou). Depois do login o
 * `app.vue` relê o shell, e a versão nova chega sozinha por aqui.
 *
 * ```vue
 * <script setup lang="ts">
 * const { is } = useExperience('para-quando')
 * </script>
 * <template>
 *   <!-- EXPERIMENT(<ref>) remove_after AAAA-MM-DD -->
 *   <WhenFirstMenu v-if="is('b')" />
 *   <MenuList v-else />
 * </template>
 * ```
 *
 * CONVENÇÃO DE ANOTAÇÃO (fiscalizada por `scripts/check_experiments.py`, na CI): toda
 * linha de código que só existe por causa de uma versão leva, logo acima, a marca
 *
 *     // EXPERIMENT(<ref>) remove_after AAAA-MM-DD
 *
 * com o mesmo `ref` e a mesma data da `ExperienceRule` (em `.vue`, dentro do
 * template, como comentário HTML; no `<script>`, com `//`). Vencida a data, a CI
 * reprova: a versão que perdeu sai do código junto com a marca (B venceu, apaga A;
 * B perdeu, apaga B). Marca malformada também reprova. Os moldes deste comentário
 * são documentação e não valem como anotação: o fiscal ignora só o molde literal,
 * com `<ref>` e `AAAA-MM-DD` escritos assim.
 *
 * A variante muda apresentação, nunca preço, disponibilidade, autorização,
 * pagamento ou promessa (X13): isso continua vindo das projeções, iguais para A e B.
 */
export function useExperience (ref: string): {
  variant: ComputedRef<string>
  is: (variant: string) => boolean
} {
  const { data } = useNuxtData<ShellResponse>(STOREFRONT_SHELL_KEY)
  const variant = computed(() => experienceVariant(data.value, ref))
  return {
    variant,
    is: (candidate: string) => variant.value === candidate
  }
}
