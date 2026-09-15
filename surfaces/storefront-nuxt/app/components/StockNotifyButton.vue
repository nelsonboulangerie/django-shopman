<script setup lang="ts">
import { notifyConfirmationMessage } from '~/presentation/stockNotify'

// "Me avise quando disponível" (WP-3). Esgotado honesto (is_notifiable) ganha um
// caminho acolhedor em vez de um "+" morto. O opt-in exige o telefone confirmado
// pela identidade canônica: anônimo entra preservando página + SKU e volta para
// uma confirmação explícita, sem redigitar o número nem confiar em texto livre.
// O estado "inscrito" PERSISTE: vem da projeção (prop subscribed).
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
const confirmationLabel = computed(() => props.name ? `Confirmar aviso recorrente para ${props.name}` : 'Confirmar aviso recorrente')
const anonymousLabel = computed(() => props.name ? `Entrar para ativar avisos recorrentes quando ${props.name} voltar` : 'Entrar para ativar avisos recorrentes')

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { isAuthenticated } = useShopSession()
const route = useRoute()
const router = useRouter()

const submitting = ref(false)
const isSubscribed = ref(!!props.subscribed)
const managementUrl = ref('')
const intendedSku = computed(() => {
  const value = route.query.aviso
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
})
const needsConfirmation = computed(() => isAuthenticated.value && intendedSku.value === props.sku && !isSubscribed.value)

async function subscribe () {
  if (submitting.value) return false
  submitting.value = true
  try {
    const result = await $fetch<{ management_url?: string }>(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {}
    })
    managementUrl.value = String(result?.management_url || '')
    isSubscribed.value = true
    if (import.meta.client) useSonner.success(notifyConfirmationMessage())
    return true
  } catch (e) {
    const detail = errorDetail(e, 'Não foi possível registrar o aviso. Tente de novo.')
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
  await router.replace({ path: route.path, query, hash: route.hash })
}

async function onAuthenticatedClick () {
  if (await subscribe()) await clearIntention()
}

async function onAnonymousClick () {
  const query = { ...route.query, aviso: props.sku }
  const next = router.resolve({ path: route.path, query, hash: route.hash }).fullPath
  if (import.meta.client) useSonner('Entre para confirmar seu WhatsApp. O produto fica guardado para a volta.')
  await navigateTo(`/entrar?next=${encodeURIComponent(next)}`)
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

  <!-- Logado: um clique assina com o telefone da conta. -->
  <template v-else-if="isAuthenticated">
    <p v-if="needsConfirmation && !compact && !pill" class="shop-meta text-muted-foreground" role="status">
      WhatsApp confirmado. Confirme para ativar este aviso.
    </p>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      :loading="submitting"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="needsConfirmation ? confirmationLabel : label"
      :title="needsConfirmation ? confirmationLabel : label"
      :autofocus="needsConfirmation"
      @click="onAuthenticatedClick"
    >
      {{ needsConfirmation ? 'Confirmar aviso' : 'Me avise' }}
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :loading="submitting"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      :aria-label="needsConfirmation ? confirmationLabel : label"
      :title="needsConfirmation ? confirmationLabel : label"
      :autofocus="needsConfirmation"
      @click="onAuthenticatedClick"
    >
      {{ needsConfirmation ? 'Confirmar aviso' : 'Me avise sempre' }}
    </UiButton>
  </template>

  <!-- Anônimo: entra pela identidade canônica e volta ao mesmo produto. -->
  <template v-else>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="anonymousLabel"
      :title="anonymousLabel"
      @click="onAnonymousClick"
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
      @click="onAnonymousClick"
    >
      Entrar para ser avisado
    </UiButton>
  </template>
</template>
