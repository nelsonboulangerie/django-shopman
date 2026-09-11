<script setup lang="ts">
import type { AccountStockAlertSubscription, AccountSummary } from '~/types/shopman'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const preferencePending = ref<Record<string, boolean>>({})
const stockAlertCancelTarget = ref<AccountStockAlertSubscription | null>(null)

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

        <UiFieldSet v-if="summary?.stock_alert_subscriptions?.length" class="rounded-lg border bg-card p-4 lg:col-span-2">
          <UiFieldLegend>Avisos de produtos</UiFieldLegend>
          <UiFieldDescription class="mb-2">
            Cada aviso vale para este produto e continua nas próximas ocorrências até você pausar ou cancelar.
          </UiFieldDescription>
          <UiFieldGroup>
            <UiField v-for="subscription in summary.stock_alert_subscriptions" :key="subscription.ref" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel>{{ subscription.product_name }}</UiFieldLabel>
                <UiFieldDescription>
                  {{ subscription.event_label }} · {{ subscription.active ? 'Ativo' : 'Pausado' }}
                </UiFieldDescription>
              </UiFieldContent>
              <div class="flex flex-wrap justify-end gap-2">
                <UiButton
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
