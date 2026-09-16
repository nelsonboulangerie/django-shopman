<script setup lang="ts">
import type { AccountStockAlertSubscription, AccountSummary } from '~/types/shopman'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const preferencePending = ref<Record<string, boolean>>({})
const stockAlertCancelTarget = ref<AccountStockAlertSubscription | null>(null)
const stockAlertConfirmTarget = ref<AccountStockAlertSubscription | null>(null)
const adultDeclared = ref(false)
const adultDeclarationError = ref('')
const { setStockNotifyState, clearStockNotifyState } = useStockNotifyTransientState()

const { data: summary, pending, refresh: refreshSummary } = await useFetch<AccountSummary>(apiPath('/api/v1/account/summary/'), {
  credentials: 'include',
  headers: requestHeaders
})

async function toggleFood (pref: { key: string, is_active: boolean }) {
  preferencePending.value = { ...preferencePending.value, [pref.key]: true }
  try {
    await $fetch(apiPath('/api/v1/account/preferences/food/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { key: pref.key, enabled: !pref.is_active }
    })
    await refreshSummary()
  } catch {
    // Falha (rede/429): re-sincroniza o switch com o servidor e avisa.
    await refreshSummary()
    if (import.meta.client) useSonner.error('Não foi possível salvar sua preferência. Tente de novo.')
  } finally {
    preferencePending.value = omitKey(preferencePending.value, pref.key)
  }
}

const notificationKeys = useState<Record<string, string>>('notification-intentions', () => ({}))

async function toggleNotification (pref: { key: string, enabled: boolean }) {
  if (preferencePending.value[pref.key]) return
  const intent = `${pref.key}:${!pref.enabled}`
  notificationKeys.value[intent] ||= newRemoteMutationKey('notification')
  preferencePending.value = { ...preferencePending.value, [pref.key]: true }
  try {
    await $fetch(apiPath('/api/v1/account/preferences/notifications/'), {
      method: 'POST',
      headers: { ...(await csrfHeaders()), 'Idempotency-Key': notificationKeys.value[intent] },
      credentials: 'include',
      body: { channel: pref.key, enabled: !pref.enabled }
    })
    notificationKeys.value = omitKey(notificationKeys.value, intent)
    await refreshSummary()
  } catch {
    await refreshSummary()
    if (import.meta.client) useSonner.error('Não foi possível salvar sua preferência. Tente de novo.')
  } finally {
    preferencePending.value = omitKey(preferencePending.value, pref.key)
  }
}

async function changeStockAlert (subscription: AccountStockAlertSubscription, action: 'pause' | 'resume' | 'cancel') {
  if (preferencePending.value[subscription.ref]) return
  preferencePending.value = { ...preferencePending.value, [subscription.ref]: true }
  try {
    await $fetch(apiPath(`/api/v1/availability/${encodeURIComponent(subscription.sku)}/notify/`), {
      method: action === 'cancel' ? 'DELETE' : 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: action === 'cancel'
        ? { subscription_ref: subscription.ref }
        : { subscription_ref: subscription.ref, action }
    })
    if (action === 'pause' || action === 'cancel') setStockNotifyState(subscription.sku, action === 'pause' ? 'paused' : 'cancelled')
    else clearStockNotifyState(subscription.sku)
    await refreshSummary()
    if (import.meta.client) {
      useSonner.success(action === 'cancel' ? 'Aviso cancelado.' : action === 'pause' ? 'Aviso pausado.' : 'Aviso retomado.')
    }
    if (action === 'cancel') stockAlertCancelTarget.value = null
  } catch (e) {
    await refreshSummary()
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível alterar este aviso.'))
  } finally {
    preferencePending.value = omitKey(preferencePending.value, subscription.ref)
  }
}

function askStockAlertConfirmation (subscription: AccountStockAlertSubscription) {
  adultDeclared.value = false
  adultDeclarationError.value = ''
  stockAlertConfirmTarget.value = subscription
}

async function confirmStockAlert () {
  const subscription = stockAlertConfirmTarget.value
  if (!subscription || preferencePending.value[subscription.ref]) return
  adultDeclarationError.value = ''
  if (!adultDeclared.value) {
    adultDeclarationError.value = 'Confirme que você tem 18 anos ou mais.'
    return
  }
  preferencePending.value = { ...preferencePending.value, [subscription.ref]: true }
  try {
    await $fetch(apiPath(`/api/v1/availability/${encodeURIComponent(subscription.sku)}/notify/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { adult_declared: true, alert_type: subscription.event_type }
    })
    clearStockNotifyState(subscription.sku)
    await refreshSummary()
    stockAlertConfirmTarget.value = null
    adultDeclared.value = false
    if (import.meta.client) useSonner.success('Aviso confirmado e ativo.')
  } catch (e) {
    await refreshSummary()
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível confirmar este aviso. Tente de novo.'))
  } finally {
    preferencePending.value = omitKey(preferencePending.value, subscription.ref)
  }
}

useSeoMeta({ title: 'Preferências' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Preferências' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div>
        <h1 class="shop-title">Preferências</h1>
        <p class="shop-muted">Conte como você gosta de ser atendido. Você pode mudar quando quiser.</p>
      </div>

      <UiSkeleton v-if="pending" class="h-48 rounded-lg" />

      <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <UiFieldSet class="rounded-lg border bg-card p-4">
          <UiFieldLegend>Preferências alimentares</UiFieldLegend>
          <UiFieldGroup>
            <UiField v-for="pref in summary?.food_preferences || []" :key="pref.key" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel :for="`food-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
              </UiFieldContent>
              <UiSwitch
                :id="`food-pref-${pref.key}`"
                :model-value="pref.is_active"
                :disabled="!!preferencePending[pref.key]"
                @update:model-value="toggleFood(pref)"
              />
            </UiField>
          </UiFieldGroup>
        </UiFieldSet>

        <UiFieldSet class="rounded-lg border bg-card p-4">
          <UiFieldLegend>Notificações</UiFieldLegend>
          <!-- A tela tem de dizer os TRÊS estados, senão ela mente num deles: o recado
               sobre o pedido em andamento sai por execução do combinado da compra, e é
               desligar a chave que o cala. Sem esta linha, quem nunca mexeu aqui vê
               tudo desligado e recebe mesmo assim. -->
          <UiFieldDescription class="mb-2">
            Recados sobre o seu pedido vão pelo canal em que você comprou: eles fazem parte da
            compra. Estas chaves valem para o resto, e desligar uma delas também cala os recados
            do pedido por ali.
          </UiFieldDescription>
          <UiFieldGroup>
            <UiField v-for="pref in summary?.notification_preferences || []" :key="pref.key" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel :for="`notification-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
                <UiFieldDescription>{{ pref.description }}</UiFieldDescription>
              </UiFieldContent>
              <UiSwitch
                :id="`notification-pref-${pref.key}`"
                :model-value="pref.enabled"
                :disabled="!!preferencePending[pref.key]"
                @update:model-value="toggleNotification(pref)"
              />
            </UiField>
          </UiFieldGroup>
        </UiFieldSet>

        <UiFieldSet v-if="summary?.stock_alert_subscriptions?.length" id="avisos-produtos" class="scroll-mt-24 rounded-lg border bg-card p-4 lg:col-span-2">
          <UiFieldLegend>Avisos de produtos</UiFieldLegend>
          <UiFieldDescription class="mb-2">
            Cada aviso vale para este produto e continua nas próximas ocorrências até você pausar ou cancelar.
          </UiFieldDescription>
          <UiFieldGroup>
            <UiField v-for="subscription in summary.stock_alert_subscriptions" :key="subscription.ref" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel>{{ subscription.product_name }}</UiFieldLabel>
                <UiFieldDescription>
                  <template v-if="subscription.requires_adult_confirmation">
                    Confirme sua maioridade novamente para voltar a receber este aviso.
                  </template>
                  <template v-else>
                    {{ subscription.event_label }} · {{ subscription.active ? 'Ativo' : 'Pausado' }}
                  </template>
                </UiFieldDescription>
              </UiFieldContent>
              <div class="flex flex-wrap justify-end gap-2">
                <UiButton
                  v-if="subscription.requires_adult_confirmation"
                  variant="outline"
                  size="sm"
                  :loading="!!preferencePending[subscription.ref]"
                  @click="askStockAlertConfirmation(subscription)"
                >
                  Confirmar novamente
                </UiButton>
                <UiButton
                  v-else
                  variant="outline"
                  size="sm"
                  :loading="!!preferencePending[subscription.ref]"
                  @click="changeStockAlert(subscription, subscription.active ? 'pause' : 'resume')"
                >
                  {{ subscription.active ? 'Pausar' : 'Retomar' }}
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="sm"
                  :disabled="!!preferencePending[subscription.ref]"
                  @click="stockAlertCancelTarget = subscription"
                >
                  Cancelar
                </UiButton>
              </div>
            </UiField>
          </UiFieldGroup>
        </UiFieldSet>
      </div>

      <BottomSheet
        :open="!!stockAlertConfirmTarget"
        max-width="sm"
        title="Confirme este aviso"
        description="Usaremos o WhatsApp confirmado na sua conta. O aviso continua ativo até você pausar ou cancelar."
        @update:open="open => { if (!open) stockAlertConfirmTarget = null }"
      >
        <form class="shop-stack-block px-4 py-4" @submit.prevent="confirmStockAlert">
          <p v-if="stockAlertConfirmTarget" class="shop-body">{{ stockAlertConfirmTarget.product_name }}</p>
          <label class="flex items-start gap-3 text-sm leading-5">
            <UiCheckbox v-model="adultDeclared" aria-label="Confirmar maioridade para este aviso" class="mt-0.5" />
            <span>Declaro ter 18 anos ou mais e quero continuar recebendo este aviso.</span>
          </label>
          <p v-if="adultDeclarationError" class="shop-meta text-destructive" role="alert">{{ adultDeclarationError }}</p>
          <UiButton
            type="submit"
            size="lg"
            class="w-full"
            icon="lucide:bell"
            :loading="!!(stockAlertConfirmTarget && preferencePending[stockAlertConfirmTarget.ref])"
          >
            Confirmar e ativar
          </UiButton>
          <UiButton
            type="button"
            variant="ghost"
            size="sm"
            class="-ml-2 self-start text-muted-foreground hover:text-foreground"
            @click="stockAlertConfirmTarget = null"
          >
            Agora não
          </UiButton>
        </form>
      </BottomSheet>

      <UiAlertDialog
        :open="!!stockAlertCancelTarget"
        @update:open="open => { if (!open) stockAlertCancelTarget = null }"
      >
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>Cancelar este aviso?</UiAlertDialogTitle>
            <UiAlertDialogDescription>
              O cancelamento é definitivo para este aviso. Mensagens já aceitas pelo provedor não podem ser retiradas.
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel>Voltar</UiAlertDialogCancel>
            <UiAlertDialogAction
              v-if="stockAlertCancelTarget"
              variant="destructive"
              :disabled="!!preferencePending[stockAlertCancelTarget.ref]"
              @click="changeStockAlert(stockAlertCancelTarget, 'cancel')"
            >
              Cancelar aviso
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
