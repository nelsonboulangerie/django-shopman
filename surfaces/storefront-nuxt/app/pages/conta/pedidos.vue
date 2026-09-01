<script setup lang="ts">
import type { OrderHistoryResponse, ReorderConflictProjection } from '~/types/shopman'
import {
  ORDER_FILTER_OPTIONS,
  orderRowEmphasisClass,
  ordersCountLabel,
  orderStatusAccentClass,
  orderStatusDotClass,
  ordersEmptyCopy,
  reorderActionFrom,
  splitOrdersByActive
} from '~/presentation/account'
import { orderTrackingRoute } from '~/utils/routes'

definePageMeta({ middleware: 'account' })

type OrderFilter = 'todos' | 'ativos' | 'anteriores'

const apiPath = useShopmanApiPath()
const { performAction, conflict, pending: reorderPending } = useReorder()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const orderFilter = ref<OrderFilter>('todos')

const { data: history, pending } = await useFetch<OrderHistoryResponse>(apiPath('/api/v1/account/orders/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: computed(() => ({ filter: orderFilter.value }))
})

const orders = computed(() => history.value?.orders ?? [])
// "Todos" separa em dois grupos: os ativos vivem em cor plena; os anteriores
// recuam (divisória + esmaecimento) sem sair do alcance.
const grouped = computed(() => splitOrdersByActive(orders.value))
const showDivider = computed(() =>
  orderFilter.value === 'todos' && grouped.value.active.length > 0 && grouped.value.past.length > 0
)
const orderedRows = computed(() =>
  orderFilter.value === 'todos' ? [...grouped.value.active, ...grouped.value.past] : orders.value
)
const countLabel = computed(() => {
  const counts = history.value?.counts
  if (!counts) return ordersCountLabel(0, orders.value.length)
  return ordersCountLabel(counts.active, counts.total)
})
// Esmaecer só faz sentido onde há contraste a fazer: no recorte "todos".
function rowClass (order: { status_tone?: string, is_active?: boolean }): string {
  const accent = orderStatusAccentClass(order.status_tone)
  if (orderFilter.value !== 'todos') return accent
  return `${accent} ${orderRowEmphasisClass(order.is_active)}`.trim()
}
// Copy do vazio vem do registro (por filtro); o fallback client-side cobre só o carregamento.
const emptyCopy = computed(() => history.value?.copy?.empty ?? ordersEmptyCopy(orderFilter.value))
const conflictRef = conflict as Ref<ReorderConflictProjection | null>
// Ação de substituição do diálogo de conflito (prefere a action 'replace'; senão a 1ª).
const conflictReplaceAction = computed(() => {
  const actions = conflictRef.value?.actions ?? []
  return actions.find(action => action.ref.includes('replace')) ?? actions[0] ?? null
})

function dismissConflict () {
  conflict.value = null
}

useSeoMeta({ title: 'Pedidos' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Pedidos' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="shop-title">Pedidos</h1>
          <p class="shop-muted">
            {{ pending ? 'Carregando…' : countLabel }}
          </p>
        </div>
        <UiSelect v-model="orderFilter">
          <UiSelectTrigger class="w-full sm:w-44" />
          <UiSelectContent>
            <UiSelectItem v-for="option in ORDER_FILTER_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </UiSelectItem>
          </UiSelectContent>
        </UiSelect>
      </div>

      <UiSkeleton v-if="pending" class="h-32 rounded-lg" />

      <UiEmpty v-else-if="!(orders || []).length" class="border">
        <UiEmptyMedia variant="icon">
          <Icon name="lucide:receipt" />
        </UiEmptyMedia>
        <UiEmptyHeader>
          <UiEmptyTitle>{{ emptyCopy.title }}</UiEmptyTitle>
          <UiEmptyDescription>{{ emptyCopy.message }}</UiEmptyDescription>
        </UiEmptyHeader>
        <div class="flex justify-center">
          <UiButton to="/menu" icon="lucide:utensils">Ver o cardápio</UiButton>
        </div>
      </UiEmpty>

      <ul v-else class="shop-stack-block">
        <template v-for="(order, index) in orderedRows" :key="order.ref">
          <!-- Divisória entre o que anda e o que já foi (só no recorte "Todos") -->
          <li
            v-if="showDivider && index === grouped.active.length"
            class="flex items-center gap-3 pt-1"
            aria-hidden="true"
          >
            <span class="h-px flex-1 bg-border" />
            <span class="shop-kicker text-muted-foreground">Finalizados</span>
            <span class="h-px flex-1 bg-border" />
          </li>
          <li
            class="flex flex-col gap-3 rounded-lg border border-l-4 bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            :class="rowClass(order)"
          >
          <div class="min-w-0">
            <p class="flex items-center gap-2 font-semibold">
              <span class="size-2 shrink-0 rounded-full" :class="orderStatusDotClass(order.status_tone)" aria-hidden="true" />
              {{ order.status_label }}
              <span v-if="order.total_display" class="text-muted-foreground">· {{ order.total_display }}</span>
            </p>
            <p class="mt-0.5 truncate shop-muted">{{ order.ref }} · {{ order.created_at_display }}</p>
          </div>
          <div class="flex shrink-0 gap-2">
            <UiButton :to="orderTrackingRoute(order.ref)" variant="outline" size="sm" icon="lucide:radar">Acompanhar</UiButton>
            <UiButton
              v-if="reorderActionFrom(order)"
              size="sm"
              icon="lucide:rotate-ccw"
              :loading="!!reorderPending[order.ref]"
              @click="performAction(reorderActionFrom(order)!)"
            >
              Refazer
            </UiButton>
          </div>
          </li>
        </template>
      </ul>

      <UiAlertDialog :open="!!conflictRef" @update:open="open => { if (!open) dismissConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflictRef?.copy.title.title || 'Sacola já tem itens' }}</UiAlertDialogTitle>
            <UiAlertDialogDescription>{{ conflictRef?.copy.message.message || conflictRef?.detail }}</UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel>Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction v-if="conflictReplaceAction" @click="performAction(conflictReplaceAction)">
              Substituir
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
