<script setup lang="ts">
// Campanhas — o que a operação dispara sozinha.
//
// O gesto mais comum é ligar/desligar, então ele fica a um toque na própria
// linha. Editar abre um workspace modal: há espaço para etapas, composições e
// prévias sem perder o contexto da campanha que originou o gesto.
import {
  audienceRulesSummary,
  choiceLabels,
  formatCount,
  platformIcon,
  platformsSummary,
} from "~/presentation/campaign";
import {
  fireActionFor,
  fireAvailability,
  fireDispatchRoute,
} from "~/presentation/campaignFire";
import { campaignEditAvailability } from "~/presentation/campaignActions";
import type {
  Campaign,
  ChosenAudience,
  MarketingCommandResponse,
} from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";
import { marketingThrottleMessage } from "~/utils/marketingRetry";
import { preserveMarketingReceipt } from "~/utils/marketingReceipt";

const {
  rules,
  actions,
  templates,
  triggers,
  platforms,
  deliveryCapabilities,
  platformLabels,
  priceTiers,
  tags,
  rfmSegments,
  products,
  offers,
  shopTimezone,
  mutatingCampaignPk,
  loading,
  error,
  refresh,
  toggle,
  patch,
  create,
} = useCampaigns();
const {
  pendingCommand: pendingFireCommand,
  begin: beginFire,
  confirm: confirmFire,
  cancel: cancelFireCommand,
} = useCampaignFireCommand();
// A prévia precisa saber se há template aprovado: com ele, o texto que sai no WhatsApp é o
// da Meta, e prometer o do modelo seria mentira.
const waTemplate = useWhatsAppTemplate();
// Prontidão por plataforma: a pílula do formulário conta ANTES do clique onde a
// campanha não vai sair. Salvar continua livre — a pré-condição é de publicar.
const { platforms: platformReadiness } = usePlatforms();
onMounted(() => {
  waTemplate.load();
});

// Rótulo de faixa e de segmento tem dono no servidor (`PriceTier.name`,
// `RFM_SEGMENTS`); a tela só consulta o mapa que a projection entrega.
const audienceLabels = computed(() => ({
  priceTiers: choiceLabels(priceTiers.value),
  tags: choiceLabels(tags.value),
  segments: choiceLabels(rfmSegments.value),
}));

// O gate de autenticação desmonta a página protegida. Estes dois valores precisam
// viver acima da instância da página: depois de entrar novamente, o operador volta
// ao mesmo editor e o rascunho local reaparece sem outro gesto nem redigitação.
const editingPk = useState<number | null>(
  "marketing-campaign-editing-pk",
  () => null,
);
const creating = useState<boolean>("marketing-campaign-creating", () => false);
const editing = computed<Campaign | null>(() =>
  editingPk.value === null
    ? null
    : (rules.value.find((rule) => rule.pk === editingPk.value) ?? null),
);
const firing = ref<Campaign | null>(null);
const fireError = ref("");
const busy = ref(false);
const draftOwner = useMarketingDraftOwner();
const route = useRoute();
const initialPromotionRef = computed(() =>
  typeof route.query.offer === "string" ? route.query.offer : "",
);

const firingTemplateRequiresProduct = computed(
  () =>
    templates.value.find(
      (template) => template.pk === firing.value?.template_id,
    )?.requires_product ?? false,
);

const PAGE_SIZE = 12;
const search = ref(typeof route.query.q === "string" ? route.query.q : "");
const stateFilter = computed(() =>
  route.query.state === "active" || route.query.state === "inactive"
    ? route.query.state
    : "",
);
const platformFilter = computed(() =>
  typeof route.query.platform === "string" ? route.query.platform : "",
);
const createdPk = computed(() => {
  const value = Number(route.query.created || 0);
  return Number.isSafeInteger(value) && value > 0 ? value : 0;
});
const currentPage = computed(() => {
  const value = Number(route.query.page || 1);
  return Number.isSafeInteger(value) && value > 0 ? value : 1;
});
const hasListFilters = computed(() =>
  Boolean(search.value.trim() || stateFilter.value || platformFilter.value),
);

function searchable(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("pt-BR");
}

const filteredRules = computed(() => {
  const term = searchable(search.value.trim());
  return rules.value
    .filter((rule) => {
      if (stateFilter.value === "active" && !rule.is_active) return false;
      if (stateFilter.value === "inactive" && rule.is_active) return false;
      if (
        platformFilter.value &&
        !rule.platforms.includes(platformFilter.value)
      )
        return false;
      if (!term) return true;
      return searchable(
        [
          rule.name,
          rule.trigger_label,
          rule.template_name,
          ...rule.platforms.map(
            (platform) => platformLabels.value[platform] ?? platform,
          ),
        ].join(" "),
      ).includes(term);
    })
    .sort(
      (a, b) =>
        Number(b.pk === createdPk.value) - Number(a.pk === createdPk.value),
    );
});
const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredRules.value.length / PAGE_SIZE)),
);
const pageRules = computed(() => {
  const page = Math.min(currentPage.value, totalPages.value);
  const start = (page - 1) * PAGE_SIZE;
  return filteredRules.value.slice(start, start + PAGE_SIZE);
});

async function replaceListQuery(
  changes: Record<string, string | number | undefined>,
) {
  const next = Object.fromEntries(
    Object.entries({ ...route.query, ...changes }).filter(
      ([, value]) => value !== "" && value !== undefined && value !== 1,
    ),
  );
  await navigateTo({ path: route.path, query: next }, { replace: true });
}

let searchTimer: ReturnType<typeof setTimeout> | null = null;
function changeSearch(value: string) {
  search.value = value;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(
    () =>
      void replaceListQuery({ q: search.value.trim() || undefined, page: 1 }),
    250,
  );
}

/** "Visto": a faixa da campanha criada sai da URL (e da tela). */
function dismissCreated() {
  void replaceListQuery({ created: undefined });
}

function changePlatform(event: Event) {
  const target = event.target;
  if (target instanceof HTMLSelectElement)
    void replaceListQuery({ platform: target.value || undefined, page: 1 });
}

function clearListFilters() {
  search.value = "";
  void replaceListQuery({
    q: undefined,
    state: undefined,
    platform: undefined,
    page: 1,
  });
}

watch(
  () => route.query.q,
  (value) => {
    search.value = typeof value === "string" ? value : "";
  },
);
watch(totalPages, (pages) => {
  if (currentPage.value > pages)
    void replaceListQuery({ page: pages === 1 ? undefined : pages });
});
onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
});

const panelOpen = computed(() => creating.value || editing.value !== null);

function fireAction(rule: Campaign) {
  return fireActionFor(rule, actions.value);
}

/** Liberado ou não, e a frase do porquê — a linha mostra a frase por extenso. */
function fireState(rule: Campaign) {
  return fireAvailability(rule, actions.value);
}

function editState(rule: Campaign) {
  return campaignEditAvailability(rule, actions.value);
}

function openNew() {
  editingPk.value = null;
  creating.value = true;
}

watch(
  () => route.query.new,
  (value) => {
    if (value === "1" && !panelOpen.value) openNew();
  },
  { immediate: true },
);

function openEdit(rule: Campaign) {
  if (!editState(rule).enabled) return;
  creating.value = false;
  editingPk.value = rule.pk;
}

async function close() {
  creating.value = false;
  editingPk.value = null;
  if (route.query.new) {
    await replaceListQuery({ new: undefined, offer: undefined });
    await nextTick();
    document.querySelector<HTMLElement>("[data-marketing-new-campaign]")?.focus();
  }
}

/** Abre "Definir público" — a campanha manual, sem esperar evento da padaria. Daqui
 *  nada é disparado: o painel cria um anúncio e leva à revisão. */
function openFire(rule: Campaign) {
  cancelFireCommand();
  fireError.value = "";
  firing.value = rule;
}

function closeFire() {
  cancelFireCommand();
  fireError.value = "";
  firing.value = null;
}

async function recordFireFailure(error: unknown) {
  const failure = httpError(error);
  const status = failure.status;
  if (status === 409) {
    await refresh();
    const current = rules.value.find((rule) => rule.pk === firing.value?.pk);
    if (current) firing.value = current;
    fireError.value =
      "A campanha mudou em outra sessão. Recarregamos os dados; aguarde a nova contagem, confira e tente novamente.";
    return;
  }
  if (status === 429) {
    const payload =
      failure.data && typeof failure.data === "object"
        ? (failure.data as Record<string, unknown>)
        : null;
    const retryAfter = Number(payload?.retry_after_seconds);
    fireError.value =
      Number.isFinite(retryAfter) && retryAfter > 0
        ? marketingThrottleMessage(retryAfter, shopTimezone.value)
        : "Muitas tentativas em pouco tempo. Aguarde alguns minutos e tente novamente. Nada foi criado.";
    return;
  }
  fireError.value = httpErrorMessage(
    error,
    "Não foi possível preparar o disparo. Nada foi criado.",
  );
}

/**
 * O disparo deu certo — a tela vai para onde o gestor já queria ir.
 *
 * O painel de sucesso era uma escala que não decidia nada: quem acabou de pedir o
 * disparo só podia tocar "Revisar anúncio agora" para chegar à revisão. Agora a
 * navegação é a resposta, e o comprovante viaja junto (`preserveMarketingReceipt`)
 * para que a revisão mostre a prova do disparo que acabou de acontecer.
 */
async function showFireResult(response: MarketingCommandResponse) {
  fireError.value = "";
  const announcementId = response.announcement.pk;
  preserveMarketingReceipt(announcementId, response.receipt);
  closeFire();
  await refresh();
  const destination = fireDispatchRoute(response);
  await navigateTo(destination);
}

async function onFire(request: {
  audience: ChosenAudience;
  sku: string;
  productLabel: string;
}) {
  if (!firing.value) return;
  const action = fireAction(firing.value);
  if (!action) {
    fireError.value =
      "A ação segura de disparo não está disponível. Atualize a lista.";
    return;
  }
  busy.value = true;
  fireError.value = "";
  try {
    const response = await beginFire({
      rule: firing.value,
      action,
      audience: request.audience,
      sku: request.sku,
      productLabel: request.productLabel,
    });
    if (response) await showFireResult(response);
  } catch (error) {
    await recordFireFailure(error);
  } finally {
    busy.value = false;
  }
}

async function onConfirmFire(value: {
  credential: string;
  typedConfirmation: string;
}) {
  busy.value = true;
  fireError.value = "";
  try {
    await showFireResult(await confirmFire(value));
  } catch (error) {
    await recordFireFailure(error);
  } finally {
    busy.value = false;
  }
}

function cancelFireConfirmation() {
  cancelFireCommand();
  fireError.value = "";
}

async function onSubmit(payload: Record<string, unknown>) {
  const resource = `campaign:${editing.value?.pk ?? "new"}`;
  busy.value = true;
  const edited = editing.value;
  const result = edited
    ? await patch(edited.pk, payload)
    : await create(payload);
  busy.value = false;
  if (!result) return;
  clearBrowserMarketingDraft({ owner: draftOwner.value, resource });
  if (edited) {
    await close();
    return;
  }
  creating.value = false;
  editingPk.value = null;
  const created = result as Campaign;
  await navigateTo(
    {
      path: "/campaigns",
      query: { created: created.pk },
    },
    { replace: true },
  );
  await nextTick();
  document
    .querySelector<HTMLElement>(`[data-created-campaign="${created.pk}"]`)
    ?.focus();
}

// A linha 2 (v3 pino 5): a situação em chips com a contagem, a plataforma num chip.
const stateCounts = computed(() => ({
  all: rules.value.length,
  active: rules.value.filter((rule) => rule.is_active).length,
  inactive: rules.value.filter((rule) => !rule.is_active).length,
}));
function setState(value: "" | "active" | "inactive") {
  void replaceListQuery({ state: value || undefined, page: undefined });
}
const platformLabel = computed(
  () => platforms.value.find((platform) => platform.value === platformFilter.value)?.label ?? "todas",
);

/** O gatilho com ícone e a frase de quando (v3: "Produção concluída / Quando um lote termina"). */
const TRIGGER_ICONS: Record<string, string> = {
  production_finished: "lucide:croissant",
  low_stock: "lucide:package-minus",
  stock_back: "lucide:package-check",
  product_created: "lucide:sparkles",
  manual: "lucide:hand",
  schedule: "lucide:calendar-clock",
};
const TRIGGER_WHEN: Record<string, string> = {
  production_finished: "Quando um lote termina",
  low_stock: "Quando o estoque fica baixo",
  stock_back: "Quando o produto volta",
  product_created: "Quando entra produto novo",
  manual: "Quando você mandar",
};
function triggerWhen(rule: Campaign): string {
  if (rule.trigger === "schedule") return rule.exhausted ? "Não dispara mais" : rule.schedule_label || "Na hora marcada";
  return TRIGGER_WHEN[rule.trigger] ?? "";
}

// O ⋯ e a ação primária na linha do título (v3 pino 4), com as teclas.
const MENU = [
  { key: "templates", label: "Modelos de texto", icon: "lucide:file-text", to: "/templates" },
  { key: "history", label: "Histórico de disparos", icon: "lucide:history", to: "/history" },
  { key: "refresh", label: "Atualizar", icon: "lucide:refresh-cw", shortcut: "R" },
];
function typing(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  return Boolean(event.ctrlKey || event.metaKey || event.altKey || target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']"));
}
onKeyStroke(["r", "R"], (event) => {
  if (typing(event)) return;
  void refresh();
});
onKeyStroke(["n", "N"], (event) => {
  if (typing(event) || panelOpen.value) return;
  event.preventDefault();
  openNew();
});

useHead({ title: "Campanhas" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <MarketingPageHeader title="Campanhas" phone-hides-actions>
      <template #search>
        <OperatorSuiteSearch
          :model-value="search"
          screen-label="filtrando as campanhas"
          placeholder="Buscar campanha, gatilho, modelo"
          aria-label="Buscar campanha"
          @update:model-value="changeSearch"
        />
      </template>
      <template #actions>
        <MarketingPageMenu heading="Campanhas" :items="MENU" @select="(key) => key === 'refresh' && refresh()" />
        <UiButton type="button" data-marketing-new-campaign @click="openNew">
          <Icon name="lucide:plus" class="size-4" aria-hidden="true" />
          Nova campanha
          <kbd class="ml-1 rounded bg-primary-foreground/20 px-1.5 text-[11px] font-semibold">N</kbd>
        </UiButton>
      </template>
      <template #phone-actions>
        <UiIconButton icon="lucide:plus" label="Nova campanha" @click="openNew" />
      </template>
      <template #filters>
        <UiFilterChip :active="!stateFilter" :count="stateCounts.all" :aria-pressed="!stateFilter" @click="setState('')">
          <template #icon><Icon v-if="!stateFilter" name="lucide:check" class="size-4 text-primary" aria-hidden="true" /></template>
          Todas
        </UiFilterChip>
        <UiFilterChip :active="stateFilter === 'active'" :count="stateCounts.active" :aria-pressed="stateFilter === 'active'" @click="setState(stateFilter === 'active' ? '' : 'active')">
          <template #icon><span class="size-2 rounded-full bg-success" aria-hidden="true" /></template>
          Ligadas
        </UiFilterChip>
        <UiFilterChip :active="stateFilter === 'inactive'" :count="stateCounts.inactive" :aria-pressed="stateFilter === 'inactive'" @click="setState(stateFilter === 'inactive' ? '' : 'inactive')">
          <template #icon><span class="size-2 rounded-full bg-muted-foreground" aria-hidden="true" /></template>
          Desligadas
        </UiFilterChip>
        <span class="mx-1 h-6 w-px bg-border" aria-hidden="true" />
        <label
          class="relative inline-flex min-h-control items-center gap-2 rounded-full border px-3 op-label transition focus-within:ring-2 focus-within:ring-ring/40"
          :class="platformFilter ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
        >
          <Icon :name="platformFilter ? platformIcon(platformFilter) : 'lucide:radio-tower'" class="size-4" aria-hidden="true" />
          Plataforma: {{ platformLabel }}
          <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
          <select :value="platformFilter" class="absolute inset-0 cursor-pointer opacity-0" aria-label="Plataforma" @change="changePlatform">
            <option value="">Todas as plataformas</option>
            <option v-for="platform in platforms" :key="platform.value" :value="platform.value">{{ platform.label }}</option>
          </select>
        </label>
        <button
          v-if="hasListFilters"
          type="button"
          class="inline-flex min-h-control items-center gap-1 px-2 op-label font-semibold text-primary"
          @click="clearListFilters"
        >
          <Icon name="lucide:x" class="size-4" aria-hidden="true" />Limpar filtros
        </button>
      </template>
    </MarketingPageHeader>
    <div class="mx-auto w-full max-w-6xl px-4 py-5">

    <div
      v-if="error && rules.length === 0"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">
        Não conseguimos carregar as campanhas.
      </p>
      <UiButton type="button" variant="link" class="mt-1" @click="refresh()">
        Tentar de novo
      </UiButton>
    </div>

    <div
      v-else-if="loading && rules.length === 0"
      class="space-y-3"
      aria-busy="true"
    >
      <UiSkeleton
        v-for="n in 3"
        :key="n"
        class="h-20 rounded-md"
        label="Carregando campanhas"
      />
    </div>

    <div
      v-else-if="rules.length === 0"
      class="rounded-md border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:sliders-horizontal"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">Nenhuma campanha ainda</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Uma campanha liga um evento da padaria a um anúncio. Comece pelo lote.
      </p>
      <UiButton type="button" class="mt-3" @click="openNew">
        <Icon name="lucide:plus" class="size-4" />
        Criar a primeira
      </UiButton>
    </div>

    <template v-else>
      <div
        v-if="createdPk"
        class="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm"
        role="status"
      >
        <div class="flex flex-wrap items-center gap-3">
          <div class="min-w-0 flex-1">
            <p class="font-semibold">Campanha criada e salva.</p>
            <p class="mt-1 text-muted-foreground">Ela está destacada na lista. Abra para conferir ou prepare o primeiro disparo.</p>
          </div>
          <UiButton type="button" variant="outline" @click="dismissCreated">
            <Icon name="lucide:check" class="size-4" aria-hidden="true" />Visto
          </UiButton>
        </div>
      </div>
      <div
        v-if="error"
        class="mb-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 text-sm"
        role="status"
      >
        <p class="font-semibold">Mostrando a última lista carregada.</p>
        <p class="mt-1 text-muted-foreground">
          Não foi possível atualizar agora. Nenhuma campanha foi alterada.
        </p>
        <UiButton type="button" variant="link" class="mt-2" @click="refresh()">
          Atualizar
        </UiButton>
      </div>

      <div
        v-if="filteredRules.length === 0"
        class="rounded-md border border-dashed border-border bg-card/50 px-6 py-8 text-center"
      >
        <Icon
          name="lucide:search-x"
          class="mx-auto size-8 text-muted-foreground"
        />
        <p class="mt-2 font-semibold">
          Nenhuma campanha combina com os filtros
        </p>
        <p class="mt-1 text-sm text-muted-foreground">
          Limpe ou ajuste os filtros para ampliar a busca.
        </p>
        <UiButton
          type="button"
          variant="link"
          class="mt-3"
          @click="clearListFilters"
        >
          Limpar filtros
        </UiButton>
      </div>

      <!-- Do desktop largo para cima, a tabela da v3 (pino 7): Campanha, Gatilho,
           Destinos, Público, a chave Ligada e "Preparar disparo". Abaixo, a lista. -->
      <div v-else class="hidden overflow-hidden rounded-lg border border-border bg-card lg:block" data-campaigns-table>
        <p class="flex items-center justify-between border-b border-border px-4 py-2 op-eyebrow text-muted-foreground">
          <span>Campanhas {{ filteredRules.length }} de {{ rules.length }}</span>
          <span class="font-normal tracking-normal normal-case">A chave liga ou desliga sem abrir.</span>
        </p>
        <table class="w-full op-label">
          <thead>
            <tr class="border-b border-border bg-muted/50 text-left op-eyebrow text-muted-foreground">
              <th class="px-4 py-2.5 font-semibold">Campanha</th>
              <th class="px-3 py-2.5 font-semibold">Gatilho</th>
              <th class="px-3 py-2.5 font-semibold">Destinos</th>
              <th class="px-3 py-2.5 font-semibold">Público</th>
              <th class="px-3 py-2.5 font-semibold"><span class="sr-only">Ligada</span></th>
              <th class="px-4 py-2.5 text-right font-semibold">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="rule in pageRules"
              :key="rule.pk"
              class="border-b border-border align-top last:border-0"
              :class="rule.pk === createdPk ? 'bg-success/5 shadow-[inset_3px_0_0_var(--success)]' : ''"
              :data-campaign-row="rule.pk"
            >
              <td class="px-4 py-3">
                <button
                  type="button"
                  class="text-left disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="!editState(rule).enabled"
                  :aria-label="editState(rule).enabled ? `Editar a campanha ${rule.name}` : `${editState(rule).reason} Campanha ${rule.name}`"
                  @click="openEdit(rule)"
                >
                  <span class="text-[15px] font-semibold" :class="rule.is_active ? '' : 'text-muted-foreground'">{{ rule.name }}</span>
                  <span v-if="!rule.requires_approval" class="ml-2 rounded-full bg-warning/10 px-2 py-0.5 op-micro font-semibold text-warning">Automática</span>
                  <span v-if="rule.pk === createdPk" class="ml-2 rounded-full bg-success/10 px-2 py-0.5 op-micro font-semibold text-success">Nova</span>
                </button>
                <p class="mt-0.5 op-micro text-muted-foreground">
                  <template v-if="rule.sent_count">Disparou {{ formatCount(rule.sent_count) }}× · {{ formatCount(rule.reached_total) }} {{ rule.reached_total === 1 ? "cliente" : "clientes" }}</template>
                  <template v-else>Ainda não disparou</template>
                  <span v-if="rule.failed_count" class="text-destructive"> · {{ formatCount(rule.failed_count) }} {{ rule.failed_count === 1 ? "falha" : "falhas" }}<template v-if="rule.last_failure">, a última por {{ rule.last_failure }}</template></span>
                </p>
              </td>
              <td class="px-3 py-3">
                <span class="inline-flex items-center gap-1.5"><Icon :name="TRIGGER_ICONS[rule.trigger] ?? 'lucide:zap'" class="size-4 text-muted-foreground" aria-hidden="true" />{{ rule.trigger_label }}</span>
                <p class="op-micro text-muted-foreground" :class="rule.exhausted ? 'text-destructive' : ''">{{ triggerWhen(rule) }}</p>
              </td>
              <td class="px-3 py-3">
                <ul class="flex flex-wrap gap-1">
                  <li v-for="platform in rule.platforms" :key="platform" class="inline-flex h-6 items-center gap-1 rounded-full border border-border px-2 op-micro font-semibold">
                    <Icon :name="platformIcon(platform)" class="size-3.5" aria-hidden="true" />{{ platformLabels[platform] ?? platform }}
                  </li>
                </ul>
              </td>
              <td class="max-w-56 px-3 py-3 op-micro text-muted-foreground">{{ audienceRulesSummary(rule.audience_rules, audienceLabels) }}</td>
              <td class="px-3 py-3">
                <label class="inline-flex items-center gap-2">
                  <UiSwitch
                    :model-value="rule.is_active"
                    :disabled="mutatingCampaignPk !== null || !editState(rule).enabled"
                    :aria-busy="mutatingCampaignPk === rule.pk"
                    :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a campanha ${rule.name}`"
                    @update:model-value="toggle(rule)"
                  />
                  <span class="font-semibold" :class="rule.is_active ? 'text-success' : 'text-muted-foreground'">{{ rule.is_active ? "Ligada" : "Desligada" }}</span>
                </label>
              </td>
              <td class="px-4 py-3 text-right">
                <UiButton
                  type="button"
                  :disabled="!fireAction(rule)?.enabled"
                  :aria-label="fireAction(rule)?.enabled ? `Preparar o disparo da campanha ${rule.name}` : `${fireState(rule).reason} Campanha ${rule.name}`"
                  variant="outline"
                  @click="openFire(rule)"
                >
                  <Icon name="lucide:send" class="size-4" aria-hidden="true" />
                  Preparar disparo
                </UiButton>
                <p v-if="!fireState(rule).enabled" class="mt-1 op-micro text-muted-foreground">{{ fireState(rule).reason }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul
        v-if="filteredRules.length"
        class="divide-y divide-border overflow-hidden rounded-md border border-border bg-card lg:hidden"
      >
        <li
          v-for="rule in pageRules"
          :key="rule.pk"
          :data-created-campaign="rule.pk === createdPk ? rule.pk : undefined"
          :tabindex="rule.pk === createdPk ? -1 : undefined"
          class="relative px-4 py-3 outline-none"
          :class="
            rule.pk === createdPk
              ? 'bg-emerald-500/5 ring-2 ring-inset ring-emerald-500/30'
              : ''
          "
        >
          <!-- Liga/desliga é o <UiSwitch> do kit: mesmo role=switch e mesmo
             aria-checked que esta página escrevia à mão, e agora o alvo de 44 px
             vem do token, não de um `size-11` que esta tela precisava lembrar. -->
          <UiSwitch
            :model-value="rule.is_active"
            :disabled="mutatingCampaignPk !== null || !editState(rule).enabled"
            :aria-busy="mutatingCampaignPk === rule.pk"
            :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a campanha ${rule.name}`"
            class="absolute top-2.5 right-3"
            @update:model-value="toggle(rule)"
          />

          <!-- A linha inteira abre a edição; o alvo amplo reduz precisão e navegação do operador. -->
          <button
            type="button"
            class="min-w-0 text-left disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!editState(rule).enabled"
            :aria-label="
              editState(rule).enabled
                ? `Editar a campanha ${rule.name}`
                : `${editState(rule).reason} Campanha ${rule.name}`
            "
            @click="openEdit(rule)"
          >
            <p
              class="pr-12 font-semibold"
              :class="rule.is_active ? '' : 'text-muted-foreground'"
            >
              {{ rule.name }}
            </p>
            <p class="mt-0.5 text-sm text-muted-foreground">
              {{ rule.trigger_label }} →
              {{ platformsSummary(rule.platforms, platformLabels) }}
            </p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              {{ audienceRulesSummary(rule.audience_rules, audienceLabels) }}
            </p>
            <!-- Desempenho onde dá para agir: a causa da falha ao lado da campanha que falhou,
               não numa lista cronológica onde ela é só lamento. -->
            <p
              v-if="rule.sent_count || rule.failed_count"
              class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs"
            >
              <span class="text-muted-foreground">
                Disparou {{ formatCount(rule.sent_count) }}× ·
                {{ formatCount(rule.reached_total) }}
                {{ rule.reached_total === 1 ? "pessoa" : "pessoas" }}
              </span>
              <span v-if="rule.failed_count" class="text-destructive">
                {{ formatCount(rule.failed_count) }}
                {{ rule.failed_count === 1 ? "falha" : "falhas"
                }}<template v-if="rule.last_failure"
                  >, a última por {{ rule.last_failure }}</template
                >
              </span>
            </p>
            <!-- Uma campanha agendada que nunca mais dispara é indistinguível de uma
               que ainda não disparou. A frase vem do servidor pronta. -->
            <p
              v-if="rule.fires_on_its_own"
              class="mt-1 inline-flex items-center gap-1 text-xs"
              :class="
                rule.exhausted ? 'text-destructive' : 'text-muted-foreground'
              "
            >
              <Icon
                :name="
                  rule.exhausted ? 'lucide:calendar-x' : 'lucide:calendar-clock'
                "
                class="size-3.5"
              />
              {{ rule.exhausted ? "Não dispara mais" : rule.schedule_label }}
            </p>
          </button>

          <div
            class="mt-2 flex min-h-11 shrink-0 items-center justify-end gap-2"
          >
            <span
              v-if="!rule.requires_approval"
              class="rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning"
              title="Publica sem passar por revisão"
            >
              Automática
            </span>
            <!-- ⚠️ Este botão NÃO dispara: ele abre "Definir público", e é o painel que
               cria um anúncio para a revisão. Por isso o rótulo visível e o nome
               acessível falam em PREPARAR — a mesma palavra que a razão do botão
               desabilitado já usava, dois centímetros abaixo.
               E o rótulo é o mesmo nos dois estados: rótulo que vira adjetivo descreve
               o botão em vez do que ele faz, e manda o gestor procurar na linha o que
               está indisponível. Quem explica o bloqueio é a frase de baixo. -->
            <UiButton
              type="button"
              :disabled="!fireAction(rule)?.enabled"
              :aria-label="
                fireAction(rule)?.enabled
                  ? `Preparar o disparo da campanha ${rule.name}`
                  : `${fireState(rule).reason} Campanha ${rule.name}`
              "
              variant="outline"
              size="xs"
              @click="openFire(rule)"
            >
              <Icon name="lucide:send" class="size-3.5" />
              Preparar disparo
            </UiButton>
            <Icon
              name="lucide:chevron-right"
              class="size-4 text-muted-foreground"
            />
          </div>
          <!-- ⚠️ A razão morava só no `title` do botão desabilitado, e o Firefox não
             mostra tooltip em botão desabilitado: "Indisponível" ficava sem porquê.
             Botão morto sem frase é defeito — a frase vai por extenso, num rodapé
             próprio. O respiro impede que a explicação invada o CTA sem criar uma
             subdivisão visual desnecessária dentro do card. -->
          <div
            v-if="!editState(rule).enabled || !fireState(rule).enabled"
            class="mt-3 space-y-1"
            data-campaign-disabled-reasons
          >
            <p
              v-if="!editState(rule).enabled"
              class="text-xs text-muted-foreground"
            >
              {{ editState(rule).reason }}
            </p>
            <p
              v-if="!fireState(rule).enabled"
              class="text-xs text-muted-foreground"
            >
              {{ fireState(rule).reason }}
            </p>
          </div>
        </li>
      </ul>

      <nav
        v-if="totalPages > 1"
        class="mt-4 grid grid-cols-2 gap-2 sm:flex sm:items-center sm:justify-between sm:gap-3"
        aria-label="Páginas de campanhas"
      >
        <UiButton
          type="button"
          variant="outline"
          class="w-full sm:w-auto"
          :disabled="currentPage <= 1"
          @click="replaceListQuery({ page: currentPage - 1 })"
        >
          Anterior
        </UiButton>
        <p
          class="col-span-2 row-start-1 text-center text-sm text-muted-foreground sm:col-auto sm:row-auto"
          role="status"
        >
          Página {{ Math.min(currentPage, totalPages) }} de {{ totalPages }} ·
          {{ filteredRules.length }} campanhas
        </p>
        <UiButton
          type="button"
          variant="outline"
          class="w-full sm:w-auto"
          :disabled="currentPage >= totalPages"
          @click="replaceListQuery({ page: currentPage + 1 })"
        >
          Próxima
        </UiButton>
      </nav>
    </template>

    <MarketingWorkspaceDialog
      :open="panelOpen"
      :title="editing ? 'Editar campanha' : 'Nova campanha'"
      description="Um evento da padaria vira um anúncio para as pessoas certas. Configure cada destino e confira as composições antes de salvar."
      @update:open="
        (v) => {
          if (!v) close();
        }
      "
    >
      <CampaignForm
        :rule="editing"
        :triggers="triggers"
        :platform-options="platforms"
        :delivery-capabilities="deliveryCapabilities"
        :templates="templates"
        :offers="offers"
        :price-tiers="priceTiers"
        :tags="tags"
        :rfm-segments="rfmSegments"
        :platform-labels="platformLabels"
        :platform-readiness="platformReadiness"
        :whatsapp-template="waTemplate.current.value"
        :busy="busy"
        :draft-owner="draftOwner"
        :shop-timezone="shopTimezone"
        :initial-promotion-ref="initialPromotionRef"
        @submit="onSubmit"
        @cancel="close"
      />
    </MarketingWorkspaceDialog>

    <!-- Disparo manual: workspace próprio, para não se confundir com editar a campanha. -->
    <MarketingWorkspaceDialog
      :open="firing !== null"
      title="Definir público"
      :description="`${firing?.name || 'Campanha'}: escolha o público. O texto vem do modelo e o anúncio nasce para revisão.`"
      @update:open="
        (v) => {
          if (!v) closeFire();
        }
      "
    >
      <div class="mx-auto w-full max-w-3xl">
        <FireCampaignPanel
          :rule="firing"
          :price-tiers="priceTiers"
          :tags="tags"
          :rfm-segments="rfmSegments"
          :products="products"
          :product-required="firingTemplateRequiresProduct"
          :busy="busy"
          :error="fireError"
          @submit="onFire"
          @cancel="closeFire"
        />
      </div>
    </MarketingWorkspaceDialog>

    <MarketingCommandConfirmationDialog
      :command="pendingFireCommand"
      :busy="busy"
      :error="pendingFireCommand ? fireError : ''"
      :shop-timezone="shopTimezone"
      @confirm="onConfirmFire"
      @cancel="cancelFireConfirmation"
    />
    </div>
  </main>
</template>
