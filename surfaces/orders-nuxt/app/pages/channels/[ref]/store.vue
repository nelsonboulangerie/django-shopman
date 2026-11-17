<script setup lang="ts">
// A loja no iFood, ao vivo (módulo Merchant). A integração CORRELACIONA (dono,
// 17/11/2026): cada coisa que a API do iFood permite se liga a um controle que o
// Shopman já tem, e a tela mostra o reflexo no iFood ao lado. Nenhum conceito novo:
//   - o toggle "Ativo" do canal (o MESMO da aba Canais, mesmo diálogo, mesmos verbos
//     Ligar e Desligar) cria e tira a pausa no iFood;
//   - o horário da casa (Admin, com os intervalos) é o horário do iFood;
//   - o calendário da casa (feriados, fechamentos) vira pausa do calendário no iFood.
// Três abas, com a aba na query (`?tab=hours`) para cada cenário abrir direto nela:
// Agora (estado e pausas), Horário (casa × iFood) e Cadastro (a loja no iFood).
// O aviso de horário divergente mora no cabeçalho, acima das abas: vale para todas.
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";
import {
  checkLook,
  hoursAlert,
  merchantLine,
  pauseHint,
  pauseListingNote,
  pauseOrigin,
  pausePeriod,
  STORE_TABS,
  storeHeadline,
  tabFromQuery,
  toneText,
  visibleChecks,
  type StoreTab,
} from "~/presentation/ifoodMerchant";
import type {
  IFoodInterruptions,
  IFoodMerchantDetail,
  IFoodMerchants,
  IFoodOpeningHours,
} from "~/types/ifoodMerchant";
import type { ChannelSwitchProjection } from "~/types/feeds";
import type { OperatorScreenAlert } from "../../../../../operator-kit/app/presentation/screenState";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const router = useRouter();
const supported = String(route.params.ref) === IFOOD_CHANNEL_REF;

const tab = computed<StoreTab>({
  get: () => tabFromQuery(route.query.tab),
  set: (value) =>
    void router.replace({ query: { ...route.query, tab: value === "now" ? undefined : value } }),
});
const tabItems = STORE_TABS.map((t) => ({ ...t }));

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
  detail.value ? storeHeadline(detail.value, pauses.value?.items ?? []) : null,
);
const checks = computed(() => (detail.value ? visibleChecks(detail.value) : []));
const storeName = computed(() => merchantLine(list.value, detail.value));
const operation = computed(() => detail.value?.operations[0] ?? null);

// O toggle "Ativo" do canal iFood: o MESMO controle da aba Canais (cor, rótulo,
// diálogo de período e motivo, gerente). Ligado aqui = ligado lá.
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
const switchColor = (sw: ChannelSwitchProjection | null | undefined) =>
  sw?.closed_by_shop ? "neutral" : "success";
const switchLabel = (sw: ChannelSwitchProjection) =>
  sw.is_active ? "iFood: ligado. Desligar…" : "iFood: desligado. Ligar…";
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
    description: `A pausa (${period}) sai do iFood agora, e a loja volta a receber pedidos se estiver no horário.`,
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
        <NuxtTabs
          v-model="tab"
          :items="tabItems"
          :content="false"
          variant="link"
          aria-label="Partes da loja no iFood"
          data-ifood-tabs
        />

        <!-- AGORA: o iFood está recebendo pedidos? O toggle do canal e as pausas. -->
        <template v-if="tab === 'now'">
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
                  <p class="text-sm" data-ifood-reason>{{ headline.reason }}</p>
                  <p class="text-xs text-muted">
                    <template v-if="operation"
                      >{{ operation.operation }} pelo
                      {{ operation.sales_channel }} ·
                    </template>
                    Consultado {{ detail?.checked_at_display }}
                  </p>
                </div>
                <label
                  v-if="ifoodSwitch"
                  class="flex items-center gap-2 text-sm font-medium"
                  data-ifood-switch-row
                >
                  Ativo
                  <NuxtSwitch
                    :color="switchColor(ifoodSwitch)"
                    :model-value="ifoodSwitch.is_active"
                    :disabled="isBusy(IFOOD_CHANNEL_REF) || !ifoodSwitch.enabled"
                    :aria-label="switchLabel(ifoodSwitch)"
                    :title="
                      ifoodSwitch.enabled
                        ? switchLabel(ifoodSwitch)
                        : ifoodSwitch.disabled_reason
                    "
                    data-ifood-switch
                    @update:model-value="switchOpen = true"
                  />
                </label>
              </div>
              <ChannelSwitchState v-if="ifoodSwitch" :sw="ifoodSwitch" />
              <ul
                v-if="checks.length"
                class="grid gap-2 sm:grid-cols-2"
                aria-label="O que o iFood confere"
              >
                <li
                  v-for="check in checks"
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

          <NuxtCard data-ifood-pauses>
            <template #header>
              <div class="flex items-center gap-2">
                <NuxtIcon name="i-lucide-pause-circle" class="size-5 text-muted" />
                <h2 class="text-base font-semibold">Pausas no iFood</h2>
              </div>
              <p class="mt-1 text-xs text-muted">
                Desligar o canal por um período vira pausa no iFood; ligar de novo tira
                a pausa. Feriados e fechamentos do calendário da casa também viram pausa.
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
        </template>

        <!-- HORÁRIO: o horário da casa (com os intervalos) é o do iFood. -->
        <NuxtCard v-else-if="tab === 'hours'" data-ifood-hours>
          <template #header>
            <div class="flex items-center gap-2">
              <NuxtIcon name="i-lucide-calendar-clock" class="size-5 text-muted" />
              <h2 class="text-base font-semibold">Horário de funcionamento</h2>
            </div>
            <p class="mt-1 text-xs text-muted">
              O horário do iFood é o horário da casa, o mesmo que a loja online e o
              checkout usam. Salvar o horário da casa grava no iFood.
            </p>
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

        <!-- CADASTRO: a loja no iFood, consulta rara. -->
        <template v-else>
          <NuxtCard data-ifood-merchants>
            <template #header>
              <h2 class="text-base font-semibold">Lojas vinculadas a este app</h2>
            </template>
            <ul v-if="list && !list.error" class="divide-y divide-default">
              <li
                v-for="m in list.merchants"
                :key="m.id"
                class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 first:pt-0 last:pb-0"
                data-ifood-merchant-row
              >
                <span class="text-sm font-medium">{{ m.name }}</span>
                <span class="min-w-0 break-all font-mono text-xs text-muted">{{ m.id }}</span>
                <NuxtBadge v-if="m.is_current" color="success" label="Esta loja" />
              </li>
              <li v-if="!list.merchants.length" class="py-2 text-sm text-muted">
                O iFood não devolveu nenhuma loja vinculada a este app.
              </li>
            </ul>
            <NuxtSkeleton v-else-if="!list" class="h-10 w-full" />
          </NuxtCard>

          <NuxtCard data-ifood-detail>
            <template #header>
              <h2 class="text-base font-semibold">Cadastro da loja no iFood</h2>
            </template>
            <div v-if="detail && !detail.detail_error" class="space-y-4">
              <div v-if="storeId" class="flex flex-wrap items-center gap-2 text-sm">
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
            <NuxtSkeleton v-else-if="!detail" class="h-40 w-full" />
          </NuxtCard>
        </template>
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
