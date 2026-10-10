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
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";
import type {
  ActiveFilters,
  FilterDimension,
} from "../../../../operator-kit/app/types/filters";

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

/** "Visto": o aviso da campanha criada sai da URL (e da tela). */
function dismissCreated() {
  void replaceListQuery({ created: undefined });
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
      path: "/settings/campaigns",
      query: { created: created.pk },
    },
    { replace: true },
  );
  await nextTick();
  document
    .querySelector<HTMLElement>(`[data-created-campaign="${created.pk}"]`)
    ?.focus();
}

// Os recortes: a situação em pílulas com a contagem (os filtros rápidos, na mesa) e,
// no painel de filtros único da suíte, a situação e a plataforma com os favoritos.
const stateCounts = computed(() => ({
  all: rules.value.length,
  active: rules.value.filter((rule) => rule.is_active).length,
  inactive: rules.value.filter((rule) => !rule.is_active).length,
}));
const STATE_LABELS = { active: "Ligadas", inactive: "Desligadas" } as const;
const stateItems = computed(() => [
  { label: "Todas", key: "all", count: stateCounts.value.all },
  { label: STATE_LABELS.active, key: "active", count: stateCounts.value.active },
  {
    label: STATE_LABELS.inactive,
    key: "inactive",
    count: stateCounts.value.inactive,
  },
]);
const stateChoice = computed<string | string[] | undefined>({
  get: () => stateFilter.value || "all",
  set: (value) => {
    const next = Array.isArray(value) ? value[0] : value;
    void replaceListQuery({
      state: next === "active" || next === "inactive" ? next : undefined,
      page: undefined,
    });
  },
});
const panelDimensions = computed<FilterDimension[]>(() => [
  {
    id: "state",
    label: "Situação",
    type: "single-select",
    options: [
      { value: "active", label: STATE_LABELS.active, count: stateCounts.value.active },
      { value: "inactive", label: STATE_LABELS.inactive, count: stateCounts.value.inactive },
    ],
  },
  {
    id: "platform",
    label: "Plataforma",
    type: "single-select",
    options: platforms.value.map((platform) => ({
      value: platform.value,
      label: platform.label,
    })),
  },
]);
// O painel e o favorito trocam a situação e a plataforma de uma vez.
const panelFilters = computed<ActiveFilters>({
  get: () => ({
    ...(stateFilter.value ? { state: [stateFilter.value] } : {}),
    ...(platformFilter.value ? { platform: [platformFilter.value] } : {}),
  }),
  set: (next) => {
    const state = next.state?.[0];
    void replaceListQuery({
      state: state === "active" || state === "inactive" ? state : undefined,
      platform: next.platform?.[0] || undefined,
      page: undefined,
    });
  },
});

// Recortes ativos: os chips removíveis do cabeçalho no celular (na mesa, os do painel,
// ao lado do botão).
const activeFilters = computed(() =>
  filterBarActiveFilters(panelDimensions.value, panelFilters.value, (next) => {
    panelFilters.value = next;
  }),
);

const countLabel = computed(() => {
  const shown = filteredRules.value.length;
  const noun = (count: number) => (count === 1 ? "campanha" : "campanhas");
  return hasListFilters.value
    ? `${formatCount(shown)} de ${formatCount(rules.value.length)} ${noun(rules.value.length)}`
    : `${formatCount(shown)} ${noun(shown)}`;
});

// O aviso da campanha recém-criada mora nas `alerts` do cabeçalho, com a saída "Visto".
const screenAlerts = computed(() =>
  createdPk.value
    ? [
        {
          id: "created",
          color: "success" as const,
          title: "Campanha criada e salva.",
          description:
            "Ela está destacada na lista. Abra para conferir ou prepare o primeiro disparo.",
          action: { label: "Visto", onSelect: dismissCreated },
        },
      ]
    : [],
);

// As colunas da mesa. Campanha é a chave (fixada, o texto quebra); Público é apoio e
// some no celular. A ordem é a da lista (a campanha recém-criada primeiro).
const campaignColumns = [
  { id: "campaign", header: "Campanha", enableHiding: false },
  { id: "trigger", header: "Gatilho" },
  { id: "platforms", header: "Destinos" },
  { id: "audience", header: "Público", meta: { supporting: true } },
  { id: "active", header: "Ligada" },
  { id: "actions", header: "Ações", enableHiding: false },
];

/** O ⋯ da linha: editar, com o motivo escrito quando a Action não deixa. */
function rowMenu(rule: Campaign) {
  const edit = editState(rule);
  return [
    {
      label: "Editar",
      icon: "i-lucide-pencil",
      disabled: !edit.enabled,
      reason: edit.enabled ? undefined : edit.reason,
      onSelect: () => openEdit(rule),
    },
  ];
}

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

// As ações da barra do topo, como dados. Na mesa, "Nova campanha" é o botão do
// `#actions` e o ⋯ guarda o resto; no celular, ela ganha a vaga de ícone e o resto
// vai para o ⋯ "Mais ações".
const headerActions = [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    kbds: ["R"],
    onSelect: () => void refresh(),
  },
  { label: "Modelos de texto", icon: "i-lucide-file-text", to: "/settings/templates" },
  { label: "Histórico de disparos", icon: "i-lucide-history", to: "/history" },
];
const phoneHeaderActions = [
  {
    label: "Nova campanha",
    icon: "i-lucide-plus",
    priority: 1,
    kbds: ["N"],
    onSelect: () => openNew(),
  },
  ...headerActions,
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
    <OperatorPageHeader
      title="Campanhas"
      :actions="headerActions"
      :phone-actions="phoneHeaderActions"
      actions-label="Mais ações de Campanhas"
      :active-filters="activeFilters"
      :clear-filters="clearListFilters"
      :alerts="screenAlerts"
      desk-only-filters
    >
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
        <NuxtButton
          icon="i-lucide-plus"
          label="Nova campanha"
          data-marketing-new-campaign
          @click="openNew"
        >
          <template #trailing><NuxtKbd value="N" /></template>
        </NuxtButton>
      </template>
      <template #filters-primary>
        <MarketingSettingsNav />
      </template>
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="panelDimensions"
          surface="marketing"
          screen="campaigns"
          data-campaign-filters
        />
      </template>
      <!-- Na mesa, a situação em pílulas com a contagem (os filtros rápidos) e a forma da
           tabela; no celular as duas moram no painel (a situação) e somem (a forma). -->
      <template #filters>
        <OperatorQuickFilters
          v-model="stateChoice"
          :items="stateItems"
          label="Situação das campanhas"
        />
        <OperatorTableView table-key="marketing-campaigns" />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <!-- A tabela da suíte: o estado (carregando, erro, vazio) é dela. A chave liga ou
           desliga sem abrir; tocar a linha abre a edição quando a Action deixa. -->
      <OperatorTable
        :data="pageRules"
        :columns="campaignColumns"
        :row-key="(rule: Campaign) => String(rule.pk)"
        :row-label="(rule: Campaign) => `a campanha ${rule.name}`"
        :row-class="(rule: Campaign) => (rule.pk === createdPk ? 'bg-success/5' : '')"
        :on-select="(rule: Campaign) => openEdit(rule)"
        :loading="loading"
        :error="Boolean(error)"
        what="as campanhas"
        :error-description="
          rules.length
            ? 'Mostrando a última lista carregada. Nenhuma campanha foi alterada.'
            : ''
        "
        :empty-icon="rules.length ? 'i-lucide-search-x' : 'i-lucide-sliders-horizontal'"
        :empty-title="
          rules.length
            ? 'Nenhuma campanha combina com os filtros.'
            : 'Nenhuma campanha ainda.'
        "
        :empty-description="
          rules.length
            ? 'Limpe ou ajuste os filtros para ampliar a busca.'
            : 'Uma campanha liga um evento da padaria a um anúncio. Comece pelo lote.'
        "
        pinned="campaign"
        view-key="marketing-campaigns"
        caption="Campanhas"
        data-campaigns-table
        @retry="refresh()"
      >
        <template #campaign-cell="{ row }">
          <div
            :data-campaign-row="row.original.pk"
            :data-created-campaign="
              row.original.pk === createdPk ? row.original.pk : undefined
            "
            :tabindex="row.original.pk === createdPk ? -1 : undefined"
            class="min-w-40 outline-none"
          >
            <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span
                class="font-semibold"
                :class="row.original.is_active ? '' : 'text-muted-foreground'"
                >{{ row.original.name }}</span
              >
              <NuxtBadge
                v-if="!row.original.requires_approval"
                color="warning"
                label="Automática"
                title="Publica sem passar por revisão"
              />
              <NuxtBadge
                v-if="row.original.pk === createdPk"
                color="success"
                label="Nova"
              />
            </span>
            <!-- Desempenho onde dá para agir: a causa da falha ao lado da campanha que
                 falhou, não numa lista cronológica onde ela é só lamento. -->
            <span class="mt-0.5 block text-xs text-muted-foreground">
              <template v-if="row.original.sent_count"
                >Disparou {{ formatCount(row.original.sent_count) }}× ·
                {{ formatCount(row.original.reached_total) }}
                {{ row.original.reached_total === 1 ? "cliente" : "clientes" }}</template
              >
              <template v-else>Ainda não disparou</template>
              <span v-if="row.original.failed_count" class="text-error">
                · {{ formatCount(row.original.failed_count) }}
                {{ row.original.failed_count === 1 ? "falha" : "falhas"
                }}<template v-if="row.original.last_failure"
                  >, a última por {{ row.original.last_failure }}</template
                ></span
              >
            </span>
          </div>
        </template>
        <template #trigger-cell="{ row }">
          <span class="inline-flex items-center gap-1.5"
            ><Icon
              :name="TRIGGER_ICONS[row.original.trigger] ?? 'lucide:zap'"
              class="size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />{{ row.original.trigger_label }}</span
          >
          <!-- Uma campanha agendada que nunca mais dispara é indistinguível de uma
               que ainda não disparou. A frase vem do servidor pronta. -->
          <span
            class="block text-xs"
            :class="row.original.exhausted ? 'text-error' : 'text-muted-foreground'"
            >{{ triggerWhen(row.original) }}</span
          >
        </template>
        <template #platforms-cell="{ row }">
          <span class="flex flex-wrap gap-1">
            <NuxtBadge
              v-for="platform in row.original.platforms"
              :key="platform"
              color="neutral"
              :label="platformLabels[platform] ?? platform"
            >
              <template #leading>
                <Icon
                  :name="platformIcon(platform)"
                  class="size-3.5"
                  aria-hidden="true"
                />
              </template>
            </NuxtBadge>
          </span>
        </template>
        <template #audience-cell="{ row }">
          <span class="block max-w-56 text-xs text-muted-foreground">{{
            audienceRulesSummary(row.original.audience_rules, audienceLabels)
          }}</span>
        </template>
        <template #active-cell="{ row }">
          <!-- Liga/desliga exige a Action `edit_campaign` exata; com um PATCH em voo,
               nenhuma outra chave mexe (o contrato do Marketing). -->
          <NuxtSwitch
            :model-value="row.original.is_active"
            :label="row.original.is_active ? 'Ligada' : 'Desligada'"
            :disabled="mutatingCampaignPk !== null || !editState(row.original).enabled"
            :loading="mutatingCampaignPk === row.original.pk"
            :aria-busy="mutatingCampaignPk === row.original.pk"
            :aria-label="`${row.original.is_active ? 'Desligar' : 'Ligar'} a campanha ${row.original.name}`"
            class="whitespace-nowrap"
            @update:model-value="toggle(row.original)"
          />
        </template>
        <template #actions-cell="{ row }">
          <div class="flex min-w-max items-center justify-end gap-1">
            <!-- ⚠️ Este botão NÃO dispara: ele abre "Definir público", e é o painel que
                 cria um anúncio para a revisão. Por isso o rótulo e o nome acessível
                 falam em PREPARAR. O rótulo é o mesmo nos dois estados; quem explica o
                 bloqueio é a frase de baixo. -->
            <NuxtButton
              icon="i-lucide-send"
              label="Preparar disparo"
              color="neutral"
              variant="outline"
              :disabled="!fireAction(row.original)?.enabled"
              :aria-label="
                fireAction(row.original)?.enabled
                  ? `Preparar o disparo da campanha ${row.original.name}`
                  : `${fireState(row.original).reason} Campanha ${row.original.name}`
              "
              @click="openFire(row.original)"
            />
            <OperatorMoreMenu
              :label="`Mais ações de ${row.original.name}`"
              :items="rowMenu(row.original)"
            />
          </div>
          <!-- ⚠️ A razão morava só no `title` do botão desabilitado, e o Firefox não
               mostra tooltip em botão desabilitado: "Indisponível" ficava sem porquê.
               Botão morto sem frase é defeito; a frase vai por extenso, sob o botão. -->
          <div
            v-if="!editState(row.original).enabled || !fireState(row.original).enabled"
            class="mt-3 max-w-64 space-y-1 text-right"
            data-campaign-disabled-reasons
          >
            <p
              v-if="!editState(row.original).enabled"
              class="text-xs text-muted-foreground"
            >
              {{ editState(row.original).reason }}
            </p>
            <p
              v-if="!fireState(row.original).enabled"
              class="text-xs text-muted-foreground"
            >
              {{ fireState(row.original).reason }}
            </p>
          </div>
        </template>
        <template #empty-actions>
          <NuxtButton
            v-if="rules.length"
            label="Limpar filtros"
            color="neutral"
            variant="outline"
            @click="clearListFilters"
          />
          <NuxtButton
            v-else
            icon="i-lucide-plus"
            label="Criar a primeira"
            @click="openNew"
          />
        </template>
        <template #footer>
          <nav
            class="flex flex-wrap items-center justify-between gap-3"
            aria-label="Páginas de campanhas"
          >
            <span
              class="text-xs text-muted-foreground tabular-nums"
              role="status"
              data-campaigns-count
              >{{ countLabel }}</span
            >
            <NuxtPagination
              v-if="totalPages > 1"
              :page="Math.min(currentPage, totalPages)"
              :total="filteredRules.length"
              :items-per-page="PAGE_SIZE"
              aria-label="Páginas"
              @update:page="(page: number) => replaceListQuery({ page })"
            />
          </nav>
        </template>
      </OperatorTable>
    </section>

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
  </main>
</template>
