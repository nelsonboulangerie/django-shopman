<script setup lang="ts">
// A loja no iFood, ao vivo (módulo Merchant). O card do canal mostra a última
// conferência; aqui a tela PERGUNTA ao iFood agora e mostra a resposta dele:
// lojas vinculadas, detalhe completo, disponibilidade, pausas e horário.
// Desligar e ligar é o toggle "Ativo" do canal (o mesmo gesto da aba Canais, com
// período, motivo e gerente). Só a pausa feita fora do Gestor (Portal do Parceiro)
// se remove aqui: é o que destrava o 409 de "já existe outra pausa no mesmo horário".
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";
import {
  availabilityLine,
  checkColor,
  hoursLine,
  operationColor,
  pauseHint,
  pauseListingNote,
  pausePeriod,
} from "~/presentation/ifoodMerchant";
import type {
  IFoodInterruptions,
  IFoodMerchantDetail,
  IFoodMerchants,
  IFoodOpeningHours,
} from "~/types/ifoodMerchant";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const channel = String(route.params.ref);
const supported = channel === IFOOD_CHANNEL_REF;

const {
  merchants,
  merchant,
  interruptions,
  hours,
  pending,
  enabled,
  refreshAll,
  followGesture,
  removePause,
  removing,
  removeError,
} = useIFoodMerchant();

// `{ enabled: false }` some das seções: a tela diz uma vez que está desligada.
const list = computed(() =>
  merchants.value?.enabled ? (merchants.value as IFoodMerchants) : null,
);
const detail = computed(() =>
  merchant.value?.enabled ? (merchant.value as IFoodMerchantDetail) : null,
);
const pauses = computed(() =>
  interruptions.value?.enabled ? (interruptions.value as IFoodInterruptions) : null,
);
const week = computed(() =>
  hours.value?.enabled ? (hours.value as IFoodOpeningHours) : null,
);

// O toggle do canal iFood, o mesmo da aba Canais.
const {
  board,
  isBusy,
  switchChannel,
  refresh: refreshBoard,
} = useFeedBoard();
const ifoodSwitch = computed(
  () =>
    board.value?.catalog_channels.find((c) => c.ref === IFOOD_CHANNEL_REF)
      ?.switch ?? null,
);
const switchOpen = ref(false);
async function submitSwitch(
  request: Parameters<typeof switchChannel>[1],
  approval?: Record<string, string>,
) {
  const outcome = await switchChannel(IFOOD_CHANNEL_REF, request, approval);
  if (outcome.ok) {
    followGesture();
    void refreshBoard();
  }
  return outcome;
}

const confirm = useConfirm();
async function askRemove(id: string, period: string) {
  const ok = await confirm({
    title: "Remover esta pausa no iFood?",
    description: `A pausa de ${period} sai do iFood agora, e a loja volta a receber pedidos se estiver no horário.`,
    confirmLabel: "Remover a pausa",
    cancelLabel: "Manter",
  });
  if (ok) await removePause(id);
}

useHead({ title: "A loja no iFood" });
const phoneHeaderActions = computed(() => [
  {
    label: "Consultar o iFood",
    icon: "i-lucide-refresh-cw",
    onSelect: () => void refreshAll(),
  },
]);
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <OperatorPageHeader
      title="A loja no iFood"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      desk-only-filters
    >
      <template #lead>
        <NuxtButton
          to="/feeds?focus=ifood"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Canais"
        />
      </template>
      <template #filters>
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Consultar o iFood"
          color="neutral"
          variant="outline"
          :loading="pending"
          data-ifood-refresh
          @click="refreshAll()"
        />
      </template>
    </OperatorPageHeader>

    <div class="min-h-0 min-w-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        v-if="!supported"
        icon="i-lucide-store"
        title="Esta tela é da loja no iFood"
        description="Os outros canais não têm loja num sistema de fora para consultar."
        :actions="[
          { label: 'Voltar para Canais', to: '/feeds', color: 'neutral', variant: 'outline' },
        ]"
      />
      <NuxtEmpty
        v-else-if="enabled === false"
        icon="i-lucide-plug-zap"
        title="A integração com a loja no iFood está desligada"
        description="Sem ela, o horário e as pausas do iFood seguem o Portal do Parceiro."
      />
      <template v-else>
        <!-- 1. Lojas vinculadas -->
        <NuxtCard as="section" aria-labelledby="ifood-merchants" data-ifood-merchants>
          <h2 id="ifood-merchants" class="font-semibold">Lojas vinculadas a este app</h2>
          <p v-if="list?.error" class="mt-2 text-sm text-error" data-section-error>
            {{ list.error }}
          </p>
          <ul v-else-if="list" class="mt-2 divide-y divide-default">
            <li
              v-for="m in list.merchants"
              :key="m.id"
              class="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2"
              data-ifood-merchant-row
            >
              <span class="font-medium">{{ m.name }}</span>
              <span class="text-xs text-muted-foreground">{{ m.corporate_name }}</span>
              <span class="font-mono text-xs text-muted-foreground">{{ m.id }}</span>
              <NuxtBadge v-if="m.is_current" color="success" label="Esta loja" />
            </li>
            <li v-if="!list.merchants.length" class="py-2 text-sm text-muted-foreground">
              O iFood não devolveu nenhuma loja vinculada a este app.
            </li>
          </ul>
          <NuxtSkeleton v-else class="mt-2 h-10 w-full" />
        </NuxtCard>

        <div class="grid gap-4 lg:grid-cols-2">
          <!-- 2. Detalhe da loja -->
          <NuxtCard as="section" aria-labelledby="ifood-detail" data-ifood-detail>
            <h2 id="ifood-detail" class="font-semibold">Detalhes da loja</h2>
            <p v-if="detail?.detail_error" class="mt-2 text-sm text-error" data-section-error>
              {{ detail.detail_error }}
            </p>
            <dl v-else-if="detail" class="mt-2 grid grid-cols-[minmax(0,13rem)_1fr] gap-x-3 gap-y-1 text-sm">
              <template v-for="row in detail.detail" :key="row.label">
                <dt class="break-words text-muted-foreground">{{ row.label }}</dt>
                <dd class="min-w-0 break-words">
                  {{ row.value }}
                  <span v-if="row.code" class="font-mono text-xs text-muted-foreground">({{ row.code }})</span>
                  <span v-if="row.hint" class="block text-xs text-muted-foreground">{{ row.hint }}</span>
                </dd>
              </template>
            </dl>
            <NuxtSkeleton v-else class="mt-2 h-40 w-full" />
          </NuxtCard>

          <!-- 3. Disponibilidade -->
          <NuxtCard as="section" aria-labelledby="ifood-status" data-ifood-status>
            <h2 id="ifood-status" class="font-semibold">Disponibilidade agora</h2>
            <template v-if="detail">
              <p v-if="detail.status_error" class="mt-2 text-sm text-error" data-section-error>
                {{ detail.status_error }}
              </p>
              <template v-else>
                <p class="mt-2 text-sm font-medium" data-ifood-availability>
                  {{ availabilityLine(detail) }}
                </p>
                <p class="text-xs text-muted-foreground">
                  Consultado às {{ detail.checked_at_display }}
                </p>
                <div
                  v-for="op in detail.operations"
                  :key="`${op.operation}-${op.sales_channel}`"
                  class="mt-3 space-y-1"
                  data-ifood-operation
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-medium">{{ op.operation }}</span>
                    <span class="text-xs text-muted-foreground">{{ op.sales_channel }}</span>
                    <NuxtBadge :color="operationColor(op.state)" :label="op.state_label" />
                  </div>
                  <p v-if="op.title" class="text-sm">
                    {{ op.title }}<span v-if="op.description">: {{ op.description }}</span>
                  </p>
                  <ul class="space-y-0.5 text-xs">
                    <li
                      v-for="check in op.checks"
                      :key="check.code"
                      class="flex flex-wrap items-center gap-2"
                    >
                      <NuxtBadge :color="checkColor(check.state)" :label="check.state_label" />
                      <span class="font-medium">{{ check.label }}</span>
                      <span class="text-muted-foreground">{{ check.title }}</span>
                      <span class="font-mono text-muted-foreground">({{ check.code }})</span>
                    </li>
                  </ul>
                </div>
              </template>
            </template>
            <NuxtSkeleton v-else class="mt-2 h-24 w-full" />
          </NuxtCard>
        </div>

        <!-- 4. Pausas -->
        <NuxtCard as="section" aria-labelledby="ifood-pauses" data-ifood-pauses>
          <div class="flex flex-wrap items-start gap-3">
            <div class="min-w-0 flex-1">
              <h2 id="ifood-pauses" class="font-semibold">Pausas no iFood</h2>
              <p class="text-xs text-muted-foreground">
                Desligar o iFood por um período vira pausa no iFood; ligar de novo tira a pausa.
              </p>
            </div>
            <NuxtButton
              v-if="ifoodSwitch"
              :label="ifoodSwitch.is_active ? 'Desligar o iFood…' : 'Ligar o iFood…'"
              :icon="ifoodSwitch.is_active ? 'i-lucide-pause' : 'i-lucide-play'"
              :color="ifoodSwitch.is_active ? 'neutral' : 'success'"
              :disabled="!ifoodSwitch.enabled || isBusy(IFOOD_CHANNEL_REF)"
              :title="ifoodSwitch.enabled ? '' : ifoodSwitch.disabled_reason"
              data-ifood-switch
              @click="switchOpen = true"
            />
          </div>
          <ChannelSwitchState v-if="ifoodSwitch" :sw="ifoodSwitch" class="mt-2" />
          <p v-if="pauses?.error" class="mt-2 text-sm text-error" data-section-error>
            {{ pauses.error }}
          </p>
          <template v-else-if="pauses">
            <p class="mt-2 text-xs text-muted-foreground">
              Pausas ativas no iFood, consultadas às {{ pauses.checked_at_display }}
            </p>
            <ul class="mt-1 divide-y divide-default">
              <li
                v-for="pause in pauses.items"
                :key="pause.id"
                class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
                data-ifood-pause
              >
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium">
                    {{ pausePeriod(pause) }}
                    <NuxtBadge
                      :color="pause.in_effect ? 'warning' : 'neutral'"
                      :label="pause.in_effect ? 'Em vigor' : 'Ainda não começou'"
                    />
                  </p>
                  <p class="text-xs text-muted-foreground">
                    {{ pause.origin_label
                    }}<span v-if="pause.description && pause.description !== pause.origin_label">
                      · {{ pause.description }}</span
                    >
                  </p>
                  <p v-if="pauseListingNote(pause)" class="text-xs text-muted-foreground" data-ifood-pause-unlisted>
                    {{ pauseListingNote(pause) }}
                  </p>
                  <p v-if="pauseHint(pause)" class="text-xs text-muted-foreground">
                    {{ pauseHint(pause) }}
                  </p>
                </div>
                <NuxtButton
                  v-if="pause.removable"
                  label="Remover"
                  icon="i-lucide-trash-2"
                  color="error"
                  variant="outline"
                  :loading="removing === pause.id"
                  data-ifood-pause-remove
                  @click="askRemove(pause.id, pausePeriod(pause))"
                />
              </li>
              <li v-if="!pauses.items.length" class="py-2 text-sm text-muted-foreground" data-ifood-no-pause>
                Nenhuma pausa ativa no iFood.
              </li>
            </ul>
            <p v-if="removeError" class="mt-2 text-sm text-error" data-ifood-remove-error>
              {{ removeError }}
            </p>
            <div v-if="pauses.refused.length" class="mt-3 space-y-1" data-ifood-refused>
              <p class="text-sm font-medium text-error">O iFood recusou estas pausas</p>
              <p v-for="(r, i) in pauses.refused" :key="i" class="text-xs">
                {{ r.origin_label }}, {{ r.starts_at_display }} até {{ r.ends_at_display }}: {{ r.error }}
              </p>
            </div>
          </template>
          <NuxtSkeleton v-else class="mt-2 h-16 w-full" />
        </NuxtCard>

        <!-- 5. Horário -->
        <NuxtCard as="section" aria-labelledby="ifood-hours" data-ifood-hours>
          <h2 id="ifood-hours" class="font-semibold">Horário de funcionamento no iFood</h2>
          <p class="text-xs text-muted-foreground">
            O horário da casa se cadastra no Admin, em Configuração › A loja › Horários e operação; salvar grava no iFood.
          </p>
          <template v-if="week">
            <p v-if="week.error" class="mt-2 text-sm text-error" data-section-error>
              {{ week.error }}
            </p>
            <p v-else class="mt-2 text-sm font-medium" data-ifood-hours-line>
              {{ hoursLine(week) }}
              <span class="text-xs font-normal text-muted-foreground">
                Consultado às {{ week.checked_at_display }}
              </span>
            </p>
            <div
              class="mt-2 grid grid-cols-[minmax(0,6rem)_1fr_1fr] gap-x-3 text-sm"
              aria-label="Horário por dia"
            >
              <span class="py-1 text-xs font-medium text-muted-foreground">Dia</span>
              <span class="py-1 text-xs font-medium text-muted-foreground">No iFood</span>
              <span class="py-1 text-xs font-medium text-muted-foreground">Na casa</span>
              <template v-for="d in week.days" :key="d.day">
                <span class="border-t border-default py-1.5 font-medium" data-ifood-hours-day>
                  {{ d.label }}
                </span>
                <span
                  class="border-t border-default py-1.5"
                  :class="!week.error && !d.matches ? 'text-warning' : ''"
                >
                  {{ week.error ? "" : d.ifood }}
                </span>
                <span class="border-t border-default py-1.5 text-muted-foreground">{{ d.house }}</span>
              </template>
            </div>
          </template>
          <NuxtSkeleton v-else class="mt-2 h-40 w-full" />
        </NuxtCard>
      </template>
    </div>

    <ChannelSwitchDialog
      :open="switchOpen && Boolean(ifoodSwitch)"
      :sw="ifoodSwitch"
      :managers="board?.managers ?? []"
      :viewer-name="board?.viewer_name ?? ''"
      :busy="isBusy(IFOOD_CHANNEL_REF)"
      :submit="submitSwitch"
      @update:open="(value: boolean) => (switchOpen = value)"
    />
  </main>
</template>
