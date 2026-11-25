<script setup lang="ts">
import type { ShellResponse } from '~/types/shopman'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'

// O SELO da versão de teste da equipe (DEV-2026-096): uma linha discreta, no rodapé e no
// topo da conta, para quem é da equipe saber que está vendo novidades em teste e poder
// ver a loja de sempre.
//
// Quem decide é o servidor: o selo só existe quando o shell traz `team_preview`, que sai
// apenas para quem vê (ou veria) uma versão fora do padrão POR SER DA EQUIPE. Cliente
// comum e anônimo não recebem o campo, e aqui nada aparece. A frase e o rótulo do botão
// vêm prontos do servidor, sem código de experimento.
//
// O botão é um comando no servidor (`POST`/`DELETE /api/v1/storefront/experience/opt-out/`,
// a escolha mora na sessão até a pessoa sair) e depois a loja relê o shell: a versão nova
// chega a toda tela pelo mesmo `useExperience` de sempre.
defineProps<{ placement: 'footer' | 'account' }>()

const { data } = useNuxtData<ShellResponse>(STOREFRONT_SHELL_KEY)
const preview = computed(() => data.value?.shell?.team_preview ?? null)

// A releitura é a do próprio shell (`refresh:manual`): o `refreshNuxtData` dispara com
// `refresh:hook`, e o `getCachedData` do shell devolveria a cópia já carregada.
const { refresh: refreshShell } = useStorefrontShell()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const switching = ref(false)

async function switchVersion () {
  const current = preview.value
  if (!current || switching.value) return
  switching.value = true
  try {
    await $fetch(apiPath('/api/v1/storefront/experience/opt-out/'), {
      method: current.opted_out ? 'DELETE' : 'POST',
      headers: await csrfHeaders(),
      credentials: 'include'
    })
    await refreshShell({ dedupe: 'cancel' })
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível trocar a versão. Tente de novo.'))
  } finally {
    switching.value = false
  }
}
</script>

<template>
  <p
    v-if="preview"
    data-team-preview
    :data-team-preview-placement="placement"
    :class="placement === 'footer' ? 'text-xs leading-5 opacity-80' : 'shop-muted text-sm leading-6'"
  >
    {{ preview.message }}
    <UiButton
      variant="link"
      data-team-preview-action
      class="h-auto p-0 align-baseline text-[length:inherit] font-semibold text-current underline"
      :disabled="switching"
      @click="switchVersion"
    >
      {{ preview.action_label }}
    </UiButton>
  </p>
</template>
