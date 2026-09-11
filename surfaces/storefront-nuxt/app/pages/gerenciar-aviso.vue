<script setup lang="ts">
interface StockAlertManagementState {
  ok: boolean
  product_name: string
  event_label: string
  state: 'active' | 'paused' | 'cancelled'
  can_pause: boolean
  can_resume: boolean
  can_cancel: boolean
  suppressed_deliveries: number
  accepted_deliveries: number
  unresolved_deliveries: number
  delivery_note: string
}

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const capability = ref('')
const alertState = ref<StockAlertManagementState | null>(null)
const pending = ref(true)
const changing = ref(false)
const error = ref('')

useSeoMeta({
  title: 'Gerenciar aviso',
  robots: 'noindex, nofollow',
})
useHead({ meta: [{ name: 'referrer', content: 'no-referrer' }] })

function capabilityHeaders(extra: Record<string, string> = {}) {
  return { ...extra, 'X-Stock-Alert-Capability': capability.value }
}

async function loadState() {
  try {
    alertState.value = await $fetch<StockAlertManagementState>(apiPath('/api/v1/stock-alert/manage/'), {
      method: 'GET',
      headers: capabilityHeaders(),
      credentials: 'include',
    })
  } catch (e) {
    error.value = errorDetail(e, 'Este link de gestão não é válido.')
  } finally {
    pending.value = false
  }
}

async function changeState(action: 'pause' | 'resume') {
  if (changing.value) return
  changing.value = true
  error.value = ''
  try {
    alertState.value = await $fetch<StockAlertManagementState>(apiPath('/api/v1/stock-alert/manage/'), {
      method: 'PATCH',
      headers: capabilityHeaders(await csrfHeaders()),
      credentials: 'include',
      body: { action },
    })
    useSonner.success(action === 'pause' ? 'Aviso pausado.' : 'Aviso retomado para as próximas ocorrências.')
  } catch (e) {
    error.value = errorDetail(e, 'Não foi possível alterar este aviso.')
  } finally {
    changing.value = false
  }
}

async function cancelAlert() {
  if (changing.value) return
  changing.value = true
  error.value = ''
  try {
    alertState.value = await $fetch<StockAlertManagementState>(apiPath('/api/v1/stock-alert/manage/'), {
      method: 'DELETE',
      headers: capabilityHeaders(await csrfHeaders()),
      credentials: 'include',
    })
    useSonner.success('Aviso cancelado.')
  } catch (e) {
    error.value = errorDetail(e, 'Não foi possível cancelar este aviso.')
  } finally {
    changing.value = false
  }
}

onMounted(() => {
  capability.value = window.location.hash.replace(/^#/, '').trim()
  window.history.replaceState(window.history.state, '', window.location.pathname)
  if (!capability.value) {
    error.value = 'Este link de gestão não é válido.'
    pending.value = false
    return
  }
  void loadState()
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container mx-auto max-w-xl shop-stack-block">
      <div>
        <h1 class="shop-title">Gerenciar este aviso</h1>
        <p class="shop-muted">Este link controla somente o aviso que veio na sua mensagem.</p>
      </div>

      <UiSkeleton v-if="pending" class="h-48 rounded-lg" />
      <UiAlert v-else-if="error" role="alert" variant="destructive">
        <UiAlertDescription>{{ error }}</UiAlertDescription>
      </UiAlert>
      <UiCard v-else-if="alertState" class="p-4">
        <div class="shop-stack-block">
          <div>
            <p class="font-semibold">{{ alertState.product_name }}</p>
            <p class="shop-muted">{{ alertState.event_label }}</p>
          </div>

          <UiAlert v-if="alertState.state === 'active'" role="status">
            <UiAlertDescription>O aviso está ativo e vale para as próximas ocorrências.</UiAlertDescription>
          </UiAlert>
          <UiAlert v-else-if="alertState.state === 'paused'" role="status" variant="warning">
            <UiAlertDescription>O aviso está pausado. Retomar vale somente para ocorrências futuras.</UiAlertDescription>
          </UiAlert>
          <UiAlert v-else role="status">
            <UiAlertDescription>O aviso foi cancelado e não pode ser retomado.</UiAlertDescription>
          </UiAlert>

          <p class="shop-meta text-muted-foreground">{{ alertState.delivery_note }}</p>
          <p v-if="alertState.unresolved_deliveries" class="shop-meta text-warning">
            Há {{ alertState.unresolved_deliveries }} envio com resultado ainda não confirmado pelo provedor.
          </p>

          <div class="flex flex-col gap-2 sm:flex-row">
            <UiButton
              v-if="alertState.can_pause"
              variant="outline"
              :loading="changing"
              icon="lucide:pause"
              @click="changeState('pause')"
            >
              Pausar aviso
            </UiButton>
            <UiButton
              v-if="alertState.can_resume"
              :loading="changing"
              icon="lucide:play"
              @click="changeState('resume')"
            >
              Retomar para próximas ocorrências
            </UiButton>
            <UiAlertDialog v-if="alertState.can_cancel">
              <UiAlertDialogTrigger as-child>
                <UiButton variant="ghost" :disabled="changing" icon="lucide:bell-off">Cancelar aviso</UiButton>
              </UiAlertDialogTrigger>
              <UiAlertDialogContent>
                <UiAlertDialogHeader>
                  <UiAlertDialogTitle>Cancelar este aviso?</UiAlertDialogTitle>
                  <UiAlertDialogDescription>
                    O cancelamento é definitivo para este aviso. Mensagens já aceitas pelo provedor não podem ser retiradas.
                  </UiAlertDialogDescription>
                </UiAlertDialogHeader>
                <UiAlertDialogFooter>
                  <UiAlertDialogCancel :disabled="changing">Voltar</UiAlertDialogCancel>
                  <UiAlertDialogAction variant="destructive" :disabled="changing" @click="cancelAlert">
                    Cancelar aviso
                  </UiAlertDialogAction>
                </UiAlertDialogFooter>
              </UiAlertDialogContent>
            </UiAlertDialog>
          </div>
        </div>
      </UiCard>

      <UiButton to="/menu" variant="ghost" icon="lucide:utensils">Voltar ao cardápio</UiButton>
    </div>
  </main>
</template>
