<script setup lang="ts">
import { notifyConfirmationMessage } from '~/presentation/stockNotify'

// O consentimento 18+ é dado uma única vez. Para anônimos ele precede o login e
// vira uma prova opaca, curta e sem PII na sessão; a volta autenticada conclui o
// mesmo gesto com a identidade canônica, sem uma segunda confirmação genérica.
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
const subscribedLabel = computed(() => props.name ? `Anotado para ${props.name}. Gerenciar aviso` : 'Anotado. Gerenciar aviso')
const anonymousLabel = computed(() => props.name ? `Ativar avisos recorrentes quando ${props.name} voltar` : 'Ativar avisos recorrentes quando voltar')

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { isAuthenticated } = useShopSession()
const route = useRoute()
const router = useRouter()

const submitting = ref(false)
const isSubscribed = ref(!!props.subscribed)
const managementUrl = ref('')
const sheetOpen = ref(false)
const adultDeclared = ref(false)
const declarationError = ref('')
const resumeFailed = ref(false)
const terminalError = ref('')
const intendedSku = computed(() => {
  const value = route.query.aviso
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
})
const intendedRef = computed(() => {
  const value = route.query.aviso_intent
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
})
const hasMatchingIntent = computed(() => intendedSku.value === props.sku && !!intendedRef.value && !isSubscribed.value)

async function subscribe (intentRef = '') {
  if (submitting.value) return false
  submitting.value = true
  resumeFailed.value = false
  try {
    const result = await $fetch<{ active?: boolean, management_url?: string }>(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: intentRef ? { intent_ref: intentRef } : { adult_declared: true }
    })
    managementUrl.value = String(result?.management_url || '')
    if (result?.active === false) {
      isSubscribed.value = false
      if (import.meta.client) useSonner('Este aviso não está ativo. Você pode ativá-lo novamente quando quiser.')
      return true
    }
    isSubscribed.value = true
    if (import.meta.client) useSonner.success(notifyConfirmationMessage())
    return true
  } catch (e) {
    const detail = errorDetail(e, 'Não foi possível registrar o aviso. Tente de novo.')
    const field = String((e as { data?: { field?: string } })?.data?.field || '')
    if (field === 'birthday') {
      terminalError.value = detail
      await clearIntention()
    }
    else resumeFailed.value = true
    if (import.meta.client) useSonner.error(detail)
    return false
  } finally {
    submitting.value = false
  }
}

async function clearIntention () {
  if (intendedSku.value !== props.sku) return
  const query = { ...route.query }
  delete query.aviso
  delete query.aviso_intent
  await router.replace({ path: route.path, query, hash: route.hash })
}

function openConsent () {
  declarationError.value = ''
  adultDeclared.value = false
  sheetOpen.value = true
}

async function onSubmit () {
  declarationError.value = ''
  if (!adultDeclared.value) {
    declarationError.value = 'Confirme que você tem 18 anos ou mais.'
    return
  }
  if (isAuthenticated.value) {
    if (!await subscribe()) return
    sheetOpen.value = false
    adultDeclared.value = false
    return
  }

  submitting.value = true
  try {
    const result = await $fetch<{ intent_ref?: string }>(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/intent/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { adult_declared: true }
    })
    const intentRef = String(result?.intent_ref || '')
    if (!intentRef) throw new Error('intent_missing')
    const query = { ...route.query, aviso: props.sku, aviso_intent: intentRef }
    const next = router.resolve({ path: route.path, query, hash: route.hash }).fullPath
    if (import.meta.client) useSonner('Agora entre para confirmar seu WhatsApp. Seu aviso fica guardado para a volta.')
    await navigateTo(`/entrar?next=${encodeURIComponent(next)}`)
  } catch (e) {
    const detail = errorDetail(e, 'Não foi possível guardar o aviso. Tente de novo.')
    if (import.meta.client) useSonner.error(detail)
  } finally {
    submitting.value = false
  }
}

async function recoverManagementLink () {
  if (!props.subscribed || isAuthenticated.value || managementUrl.value) return false
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

async function initialize () {
  await recoverManagementLink()
  if (!isAuthenticated.value || intendedSku.value !== props.sku || isSubscribed.value) return
  if (!intendedRef.value) {
    openConsent()
    return
  }
  if (await subscribe(intendedRef.value)) await clearIntention()
}

async function restartIntent () {
  await clearIntention()
  resumeFailed.value = false
  openConsent()
}

onMounted(initialize)

const managementHref = computed(() => managementUrl.value || (isAuthenticated.value ? '/conta/preferencias#avisos-produtos' : ''))
</script>

<template>
  <!-- Estado confirmado (persistente): calmo, sem ação pendente. -->
  <UiButton
    v-if="isSubscribed"
    :to="managementHref || undefined"
    :disabled="!managementHref"
    :variant="pill ? 'default' : 'outline'"
    :size="pill ? 'sm' : (compact ? 'sm' : 'lg')"
    icon="lucide:bell-ring"
    :class="[
      pill ? 'h-10 w-full justify-center gap-1 rounded-full bg-cta px-3 text-sm tracking-tight text-cta-foreground shadow-sm' : (compact ? '' : 'w-full'),
      'disabled:opacity-100',
      !pill && (inverted ? 'shop-action-inverted' : 'border-primary text-primary')
    ]"
    :aria-label="subscribedLabel"
    :title="subscribedLabel"
  >
    Anotado
  </UiButton>

  <!-- Logado: retorno do login retoma a prova; uso comum pede a declaração. -->
  <template v-else-if="isAuthenticated">
    <p v-if="terminalError && !compact && !pill" class="shop-meta text-destructive" role="alert">
      {{ terminalError }}
    </p>
    <p v-else-if="hasMatchingIntent && submitting && !compact && !pill" class="shop-meta text-muted-foreground" role="status">
      WhatsApp confirmado. Estamos anotando seu aviso…
    </p>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      :loading="submitting"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :disabled="!!terminalError"
      :aria-label="label"
      :title="label"
      @click="hasMatchingIntent && resumeFailed ? restartIntent() : openConsent()"
    >
      {{ hasMatchingIntent && resumeFailed ? 'Tentar de novo' : 'Me avise' }}
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :loading="submitting"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      :disabled="!!terminalError"
      :aria-label="label"
      :title="label"
      @click="hasMatchingIntent && resumeFailed ? restartIntent() : openConsent()"
    >
      {{ hasMatchingIntent && resumeFailed ? 'Tentar ativar aviso' : 'Me avise sempre' }}
    </UiButton>
  </template>

  <!-- Anônimo: declara 18+ uma vez e então entra pela identidade canônica. -->
  <template v-else>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="anonymousLabel"
      :title="anonymousLabel"
      @click="openConsent"
    >
      Me avise
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      :aria-label="anonymousLabel"
      :title="anonymousLabel"
      @click="openConsent"
    >
      Me avise sempre
    </UiButton>
  </template>

  <BottomSheet
    v-model:open="sheetOpen"
    max-width="sm"
    title="Ative seu aviso"
    :description="isAuthenticated
      ? 'Usaremos o WhatsApp confirmado na sua conta. O aviso continua ativo até você pausar ou cancelar.'
      : 'Confirme a maioridade uma única vez. Depois de entrar, concluiremos o aviso automaticamente com seu WhatsApp confirmado.'"
    data-stock-notify-sheet
  >
    <form class="shop-stack-block px-4 py-4" @submit.prevent="onSubmit">
      <label class="flex items-start gap-3 text-sm leading-5">
        <UiCheckbox v-model="adultDeclared" aria-label="Confirmar maioridade" class="mt-0.5" />
        <span>Declaro ter 18 anos ou mais e quero receber estes avisos.</span>
      </label>
      <p v-if="declarationError" class="shop-meta text-destructive" role="alert">{{ declarationError }}</p>
      <UiButton type="submit" size="lg" class="w-full" :loading="submitting" icon="lucide:bell">
        {{ isAuthenticated ? 'Ativar aviso' : 'Continuar para entrar' }}
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
