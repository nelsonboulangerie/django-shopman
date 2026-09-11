<script setup lang="ts">
import { maskPhoneInput, normalizeAuthPhone } from '~/utils/authPhone'
import { notifyConfirmationMessage, notifyPhoneTarget } from '~/presentation/stockNotify'

// "Me avise quando disponível" (WP-3). Esgotado honesto (is_notifiable) ganha um
// caminho acolhedor em vez de um "+" morto: logado assina com 1 clique (usa o
// telefone da conta); anônimo informa só o telefone num bottom-sheet canônico
// (mesmo figurino dos demais overlays, dismiss explícito). Omotenashi: oferecer,
// nunca bloquear seco. O estado "inscrito" PERSISTE: vem da projeção (prop subscribed).
const props = defineProps<{
  sku: string
  // Nome do produto — usado em aria-label/tooltip (acessibilidade entre muitos cards).
  name?: string
  // Cards usam a forma enxuta (sino + rótulo curto); a PDP usa o bloco largo.
  compact?: boolean
  // Sobre o card escuro flutuante (CTA mobile): botão vira Faubourg + texto Brass
  // escuro (.shop-action-inverted) e o estado confirmado fica claro.
  inverted?: boolean
  // Pill sobre a foto (lista do cardápio): rounded-full com sino + rótulo.
  pill?: boolean
  // Persistência: cliente já inscrito (vem da projeção). Inicializa o estado.
  subscribed?: boolean
}>()

const label = computed(() => props.name ? `Ativar avisos recorrentes quando ${props.name} voltar` : 'Ativar avisos recorrentes quando voltar')
const subscribedLabel = computed(() => props.name ? `Aviso recorrente ativo para ${props.name}` : 'Aviso recorrente ativo')

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { isAuthenticated, publicConfig } = useShopSession()
const defaultDdd = computed(() => publicConfig.value?.default_ddd || '')

const submitting = ref(false)
const isSubscribed = ref(!!props.subscribed)
const requestReceived = ref(false)
const managementUrl = ref('')
const sheetOpen = ref(false)
const phoneInput = ref('')
const phoneError = ref('')

const phone = computed({
  get: () => phoneInput.value,
  set: (value: string) => { phoneInput.value = maskPhoneInput(value, 'BR') }
})

// O número que a casa vai usar, de volta na tela antes do envio. A normalização
// completa o DDD e repara celular antigo de 10 dígitos — quem digitou não vê
// isso acontecer, e um palpite errado manda a mensagem para outra pessoa.
const notifyTarget = computed(() => notifyPhoneTarget(phoneInput.value, defaultDdd.value))

async function subscribe (phoneValue: string) {
  if (submitting.value) return
  submitting.value = true
  phoneError.value = ''
  try {
    const result = await $fetch<{ management_url?: string }>(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: phoneValue ? { phone: phoneValue } : {}
    })
    managementUrl.value = String(result?.management_url || '')
    if (!isAuthenticated.value && !managementUrl.value) await recoverManagementLink(true)
    isSubscribed.value = isAuthenticated.value || !!managementUrl.value
    requestReceived.value = !isSubscribed.value
    sheetOpen.value = false
    if (import.meta.client) useSonner.success(notifyConfirmationMessage(phoneValue))
  } catch (e) {
    const { data } = httpError(e)
    const detail = errorDetail(e, 'Não foi possível registrar o aviso. Tente de novo.')
    if (data?.field === 'phone') phoneError.value = detail
    else if (import.meta.client) useSonner.error(detail)
  } finally {
    submitting.value = false
  }
}

function onAuthenticatedClick () {
  subscribe('')
}

function onAnonymousSubmit () {
  const normalized = normalizeAuthPhone(phoneInput.value, 'BR', defaultDdd.value)
  if (!normalized) {
    phoneError.value = 'Informe um telefone com DDD.'
    return
  }
  subscribe(normalized)
}

async function recoverManagementLink (force = false) {
  if ((!force && !props.subscribed) || isAuthenticated.value || managementUrl.value) return false
  try {
    const result = await $fetch<{ active: boolean, management_url: string }>(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/`), {
      method: 'GET',
      credentials: 'include'
    })
    managementUrl.value = String(result?.management_url || '')
    return !!managementUrl.value
  } catch {
    // A projeção continua sendo a fonte do estado visual. A ausência de uma
    // sessão recuperável não transforma falha de rede em nova assinatura.
    return false
  }
}

onMounted(recoverManagementLink)

const managementHref = computed(() => managementUrl.value || (isAuthenticated.value ? '/conta/preferencias#avisos-produtos' : ''))
</script>

<template>
  <!-- Estado confirmado (persistente): calmo, sem ação pendente. -->
  <template v-if="isSubscribed">
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell-ring"
      disabled
      class="h-10 w-full justify-center gap-1 rounded-full bg-cta px-3 text-sm tracking-tight text-cta-foreground shadow-sm disabled:opacity-100"
      :aria-label="subscribedLabel"
      :title="subscribedLabel"
    >
      Anotado
    </UiButton>
    <UiButton
      v-else
      variant="outline"
      :size="compact ? 'sm' : 'lg'"
      icon="lucide:bell-ring"
      disabled
      :class="[compact ? '' : 'w-full', 'disabled:opacity-100', inverted ? 'shop-action-inverted' : 'border-primary text-primary']"
      :aria-label="subscribedLabel"
      :title="subscribedLabel"
    >
      Aviso ativo
    </UiButton>
    <UiButton
      v-if="managementHref"
      :to="managementHref"
      variant="ghost"
      size="sm"
      icon="lucide:settings-2"
    >
      Gerenciar este aviso
    </UiButton>
  </template>

  <!-- Repetição anônima em outra sessão recebe confirmação neutra: telefone +
       SKU não concedem nem revelam a capacidade de uma assinatura existente. -->
  <template v-else-if="requestReceived">
    <UiButton
      :size="compact ? 'sm' : 'lg'"
      variant="outline"
      icon="lucide:check"
      disabled
      :class="[compact ? '' : 'w-full', 'disabled:opacity-100']"
      aria-label="Pedido de aviso recebido"
    >
      Pedido recebido
    </UiButton>
  </template>

  <!-- Logado: um clique assina com o telefone da conta. -->
  <template v-else-if="isAuthenticated">
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      :loading="submitting"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="label"
      :title="label"
      @click="onAuthenticatedClick"
    >
      Me avise
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :loading="submitting"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      :aria-label="label"
      :title="label"
      @click="onAuthenticatedClick"
    >
      Me avise sempre
    </UiButton>
  </template>

  <!-- Anônimo: bottom-sheet pede só o telefone (mesmo figurino dos demais overlays). -->
  <template v-else>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="label"
      :title="label"
      @click="sheetOpen = true"
    >
      Me avise
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      :aria-label="label"
      :title="label"
      @click="sheetOpen = true"
    >
      Me avise sempre
    </UiButton>
    <BottomSheet
      v-model:open="sheetOpen"
      max-width="sm"
      title="Avisamos quando estiver disponível"
      description="Deixe seu WhatsApp para receber um aviso a cada nova ocorrência elegível deste produto. O aviso continua ativo até você pausar ou cancelar."
      data-stock-notify-sheet
    >
      <form class="shop-stack-block px-4 py-4" @submit.prevent="onAnonymousSubmit">
        <UiInput
          v-model="phone"
          type="tel"
          inputmode="tel"
          autocomplete="tel"
          placeholder="(43) 99999-0000"
          aria-label="Telefone para aviso"
          class="bg-background"
        />
        <p v-if="phoneError" class="shop-meta text-destructive">{{ phoneError }}</p>
        <p v-else-if="notifyTarget" class="shop-meta text-muted-foreground">
          Mandaremos a mensagem para <span class="font-semibold text-foreground">{{ notifyTarget }}</span>. Se não for esse o número, é só corrigir aqui.
        </p>
        <UiButton type="submit" size="lg" class="w-full" :loading="submitting" icon="lucide:bell">
          Avise-me
        </UiButton>
        <UiButton
          type="button"
          variant="ghost"
          size="sm"
          class="-ml-2 self-start text-muted-foreground hover:text-foreground"
          @click="sheetOpen = false"
        >
          Agora não
        </UiButton>
      </form>
    </BottomSheet>
  </template>
</template>
