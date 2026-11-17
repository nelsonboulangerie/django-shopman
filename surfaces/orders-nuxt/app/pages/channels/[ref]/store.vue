<script setup lang="ts">
// A loja no iFood, ao vivo (módulo Merchant). A tela responde, antes de tudo, a
// pergunta do operador: "o iFood está recebendo pedidos agora?". Logo abaixo, o que
// é rotina (pausas e horário); o cadastro da loja no iFood fica no fim, recolhido.
// Desligar e ligar é o toggle "Ativo" do canal (o mesmo diálogo de período, motivo e
// gerente da aba Canais). Só a pausa feita fora do Gestor (Portal do Parceiro) se
// remove aqui: é o que destrava o 409 de "já existe outra pausa no mesmo horário".
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";
import {
  checkLook,
  hoursAlert,
  merchantLine,
  pauseHint,
  pauseListingNote,
  pauseOrigin,
  pausePeriod,
  storeHeadline,
  toneText,
} from "~/presentation/ifoodMerchant";
import type {
  IFoodInterruptions,
  IFoodMerchantDetail,
  IFoodMerchants,
  IFoodOpeningHours,
} from "~/types/ifoodMerchant";
import type { OperatorScreenAlert } from "../../../../../operator-kit/app/presentation/screenState";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const supported = String(route.params.ref) === IFOOD_CHANNEL_REF;

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
  writeHours,
  writing,
  writeError,
} = useIFoodMerchant();

// `{ enabled: false }` some das seções: a tela diz uma vez que está desligada.
const list = computed(() =>
  merchants.value?.enabled ? (merchants.value as IFoodMerchants) : null,
);
const detail = computed(() =>
  merchant.value?.enabled ? (merchant.value as IFoodMerchantDetail) : null,
);
const pauses = computed(() =>
  interruptions.value?.enabled
    ? (interruptions.value as IFoodInterruptions)
    : null,
);
const week = computed(() =>
  hours.value?.enabled ? (hours.value as IFoodOpeningHours) : null,
);

const headline = computed(() =>
  detail.value ? storeHeadline(detail.value) : null,
);
const storeName = computed(() => merchantLine(list.value, detail.value));
const operation = computed(() => detail.value?.operations[0] ?? null);

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

// O que a tela precisa que a pessoa saiba agora: um lugar só, o cabeçalho.
const screenAlerts = computed<OperatorScreenAlert[]>(() => {
  const out: OperatorScreenAlert[] = [];
  const failures = [
    list.value?.error,
    detail.value?.detail_error,
    pauses.value?.error,
    week.value?.error,
  ].filter(Boolean) as string[];
  if (failures.length)
    out.push({
      id: `fail:${failures[0]}`,
      color: "error",
      title: failures[0]!,
      description: "O resto da tela mostra o que o iFood respondeu.",
      action: { label: "Consultar de novo", onSelect: () => void refreshAll() },
    });
  for (const msg of [writeError.value, removeError.value].filter(Boolean))
    out.push({ id: `gesture:${msg}`, color: "error", title: msg });
  for (const refused of pauses.value?.refused ?? [])
    out.push({
      id: `refused:${refused.starts_at_display}`,
      color: "error",
      title: "O iFood recusou uma pausa",
      description: `${refused.origin_label}, ${refused.starts_at_display} até ${refused.ends_at_display}. ${refused.error}`,
    });
  const hoursNotice = week.value
    ? hoursAlert(week.value, () => void writeHours())
    : null;
  if (hoursNotice) out.push(hoursNotice);
  return out;
});

// O cadastro: o ID com botão de copiar; o resto em pares rótulo e valor.
const storeId = computed(
  () => detail.value?.detail.find((r) => r.label === "ID da loja")?.value ?? "",
);
const registry = computed(
  () => detail.value?.detail.filter((r) => r.label !== "ID da loja") ?? [],
);
const copied = ref(false);
async function copyId() {
  try {
    await navigator.clipboard.writeText(storeId.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
  } catch {
    copied.value = false;
  }
}

const runtimeConfig = useRuntimeConfig();
const adminHours = `${String(runtimeConfig.public.adminBaseUrl ?? "")}/admin/shop/shopoperation/`;

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
      :alerts="screenAlerts"
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
      <template #subtitle>
        <span
          v-if="storeName"
          class="truncate text-xs text-muted"
          data-ifood-store-name
          >{{ storeName }}</span
        >
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

    <div class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6">
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
      <div v-else class="flex flex-col gap-4">
        <!-- 1. A resposta: o iFood está recebendo pedidos? -->
        <NuxtCard data-ifood-headline>
          <div v-if="headline" class="flex flex-col gap-4">
            <div class="flex flex-wrap items-start gap-3">
              <NuxtIcon
                :name="headline.icon"
                class="mt-0.5 size-7 shrink-0"
                :class="toneText(headline.tone)"
              />
              <div class="min-w-0 flex-1 space-y-1">
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="text-base font-semibold" data-ifood-availability>
                    {{ headline.title }}
                  </h2>
                  <NuxtBadge :color="headline.tone" :label="headline.badge" />
                </div>
                <p class="text-sm">{{ headline.reason }}</p>
                <p class="text-xs text-muted">
                  <template v-if="operation"
                    >{{ operation.operation }} pelo
                    {{ operation.sales_channel }} ·
                  </template>
                  Consultado {{ detail?.checked_at_display }}
                </p>
              </div>
              <NuxtButton
                v-if="ifoodSwitch"
                :label="
                  ifoodSwitch.is_active ? 'Desligar o iFood…' : 'Ligar o iFood…'
                "
                :icon="ifoodSwitch.is_active ? 'i-lucide-pause' : 'i-lucide-play'"
                :color="ifoodSwitch.is_active ? 'neutral' : 'primary'"
                :disabled="!ifoodSwitch.enabled || isBusy(IFOOD_CHANNEL_REF)"
                :title="ifoodSwitch.enabled ? '' : ifoodSwitch.disabled_reason"
                class="w-full sm:w-auto"
                data-ifood-switch
                @click="switchOpen = true"
              />
            </div>
            <ChannelSwitchState v-if="ifoodSwitch" :sw="ifoodSwitch" />
            <ul
              v-if="operation?.checks.length"
              class="grid gap-2 sm:grid-cols-2"
              aria-label="O que o iFood confere"
            >
              <li
                v-for="check in operation.checks"
                :key="check.code"
                class="flex items-start gap-2 text-sm"
                data-ifood-check
              >
                <NuxtIcon
                  :name="checkLook(check).icon"
                  class="mt-0.5 size-4 shrink-0"
                  :class="toneText(checkLook(check).tone)"
                />
                <span class="min-w-0">
                  <span class="font-medium">{{ check.label }}</span>
                  <span class="block text-xs text-muted">{{ check.title }}</span>
                </span>
              </li>
            </ul>
          </div>
          <div v-else class="space-y-3">
            <NuxtSkeleton class="h-7 w-2/3" />
            <NuxtSkeleton class="h-4 w-1/2" />
            <NuxtSkeleton class="h-16 w-full" />
          </div>
        </NuxtCard>

        <div class="grid items-start gap-4 lg:grid-cols-2">
          <!-- 2. Pausas: a rotina -->
          <NuxtCard data-ifood-pauses>
            <template #header>
              <div class="flex items-center gap-2">
                <NuxtIcon name="i-lucide-pause-circle" class="size-5 text-muted" />
                <h2 class="text-base font-semibold">Pausas no iFood</h2>
              </div>
              <p class="mt-1 text-xs text-muted">
                Desligar o iFood por um período vira pausa no iFood; ligar de novo tira
                a pausa.
              </p>
            </template>
            <template v-if="pauses && !pauses.error">
              <ul v-if="pauses.items.length" class="divide-y divide-default">
                <li
                  v-for="pause in pauses.items"
                  :key="pause.id"
                  class="flex flex-wrap items-start gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0"
                  data-ifood-pause
                >
                  <div class="min-w-0 flex-1 space-y-0.5">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-sm font-medium">{{ pausePeriod(pause) }}</span>
                      <NuxtBadge
                        :color="pause.in_effect ? 'warning' : 'neutral'"
                        :label="pause.in_effect ? 'Em vigor' : 'Ainda não começou'"
                      />
                    </div>
                    <p class="text-xs text-muted">{{ pauseOrigin(pause) }}</p>
                    <p
                      v-if="pauseListingNote(pause)"
                      class="text-xs text-muted"
                      data-ifood-pause-unlisted
                    >
                      {{ pauseListingNote(pause) }}
                    </p>
                    <p v-if="pauseHint(pause)" class="text-xs text-muted">
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
              </ul>
              <div
                v-else
                class="flex items-center gap-2 text-sm text-muted"
                data-ifood-no-pause
              >
                <NuxtIcon name="i-lucide-circle-check" class="size-4 text-success" />
                Nenhuma pausa no iFood agora.
              </div>
              <p class="mt-3 text-xs text-muted">
                Consultado {{ pauses.checked_at_display }}
              </p>
            </template>
            <NuxtSkeleton v-else-if="!pauses" class="h-16 w-full" />
          </NuxtCard>

          <!-- 3. Horário: o do iFood ao lado do da casa -->
          <NuxtCard data-ifood-hours>
            <template #header>
              <div class="flex items-center gap-2">
                <NuxtIcon name="i-lucide-calendar-clock" class="size-5 text-muted" />
                <h2 class="text-base font-semibold">Horário de funcionamento</h2>
              </div>
            </template>
            <template v-if="week">
              <div
                class="grid grid-cols-[minmax(0,5.5rem)_1fr_1fr] gap-x-3 text-sm"
                role="table"
                aria-label="Horário por dia, no iFood e na casa"
              >
                <div role="row" class="contents">
                  <span role="columnheader" class="pb-2 text-xs font-medium text-muted">Dia</span>
                  <span role="columnheader" class="pb-2 text-xs font-medium text-muted">No iFood</span>
                  <span role="columnheader" class="pb-2 text-xs font-medium text-muted">Na casa</span>
                </div>
                <div
                  v-for="d in week.days"
                  :key="d.day"
                  role="row"
                  class="contents"
                  data-ifood-hours-day
                >
                  <span role="cell" class="border-t border-default py-2 font-medium">{{
                    d.label
                  }}</span>
                  <span
                    role="cell"
                    class="flex flex-wrap items-center gap-1.5 border-t border-default py-2"
                  >
                    <template v-if="!week.error">
                      {{ d.ifood }}
                      <NuxtBadge v-if="!d.matches" color="warning" label="Diferente" />
                    </template>
                    <span v-else class="text-muted">Sem resposta</span>
                  </span>
                  <span role="cell" class="border-t border-default py-2 text-muted">{{
                    d.house
                  }}</span>
                </div>
              </div>
              <p class="mt-3 text-xs text-muted">
                Consultado {{ week.checked_at_display
                }}<template v-if="week.written_at_display">
                  · gravado no iFood {{ week.written_at_display }}</template
                >
              </p>
            </template>
            <NuxtSkeleton v-else class="h-48 w-full" />
            <template #footer>
              <div class="flex flex-wrap gap-2">
                <NuxtButton
                  label="Gravar no iFood"
                  icon="i-lucide-upload"
                  color="neutral"
                  variant="outline"
                  :loading="writing"
                  :disabled="!week || !week.governs"
                  data-ifood-hours-write
                  @click="writeHours()"
                />
                <NuxtButton
                  label="Mudar o horário da casa"
                  icon="i-lucide-external-link"
                  color="neutral"
                  variant="ghost"
                  :to="adminHours"
                  target="_blank"
                />
              </div>
            </template>
          </NuxtCard>
        </div>

        <!-- 4. O cadastro, recolhido: consulta rara -->
        <NuxtCard data-ifood-detail>
          <NuxtCollapsible>
            <NuxtButton
              label="Cadastro da loja no iFood"
              icon="i-lucide-id-card"
              trailing-icon="i-lucide-chevron-down"
              color="neutral"
              variant="ghost"
              class="-mx-2.5 justify-start"
              block
            />
            <template #content>
              <p v-if="detail?.detail_error" class="mt-3 text-sm text-error">
                {{ detail.detail_error }}
              </p>
              <div v-else-if="detail" class="mt-3 space-y-4">
                <div
                  v-if="storeId"
                  class="flex flex-wrap items-center gap-2 text-sm"
                >
                  <span class="text-muted">ID da loja</span>
                  <span class="min-w-0 break-all font-mono text-xs">{{ storeId }}</span>
                  <NuxtButton
                    :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
                    :aria-label="copied ? 'ID copiado' : 'Copiar o ID da loja'"
                    color="neutral"
                    variant="ghost"
                    square
                    @click="copyId()"
                  />
                </div>
                <dl class="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                  <div
                    v-for="row in registry"
                    :key="row.label"
                    class="grid grid-cols-[minmax(0,8.5rem)_1fr] gap-x-3"
                  >
                    <dt class="text-muted">{{ row.label }}</dt>
                    <dd
                      class="min-w-0 break-words"
                      :title="row.code ? `Código do iFood: ${row.code}` : undefined"
                    >
                      {{ row.value }}
                      <span v-if="row.hint" class="block text-xs text-muted">{{
                        row.hint
                      }}</span>
                    </dd>
                  </div>
                </dl>
              </div>
            </template>
          </NuxtCollapsible>
        </NuxtCard>
      </div>
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
