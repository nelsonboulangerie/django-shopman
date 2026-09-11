<script setup lang="ts">
// Campanhas — o que a operação dispara sozinha.
//
// O gesto mais comum é ligar/desligar, então ele fica a um toque na própria
// linha. Editar abre um painel lateral: a lista continua visível, e o gestor
// não perde o contexto de quais outras campanhas já existem.
import {
  audienceRulesSummary,
  choiceLabels,
  formatCount,
  platformsSummary,
} from "~/presentation/campaign";
import type {
  Campaign,
  ChosenAudience,
  MarketingCommandResponse,
} from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";

const {
  rules,
  actions,
  templates,
  triggers,
  platforms,
  platformLabels,
  priceTiers,
  tags,
  rfmSegments,
  products,
  offers,
  shopTimezone,
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
    : rules.value.find((rule) => rule.pk === editingPk.value) ?? null,
);
const firing = ref<Campaign | null>(null);
const fireResult = ref<MarketingCommandResponse | null>(null);
const fireError = ref("");
const busy = ref(false);
const draftOwner = useMarketingDraftOwner();
const route = useRoute();

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
const currentPage = computed(() => {
  const value = Number(route.query.page || 1);
  return Number.isSafeInteger(value) && value > 0 ? value : 1;
});
const hasListFilters = computed(
  () => Boolean(search.value.trim() || stateFilter.value || platformFilter.value),
);

function searchable(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("pt-BR");
}

const filteredRules = computed(() => {
  const term = searchable(search.value.trim());
  return rules.value.filter((rule) => {
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
  });
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
function changeSearch(event: Event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  search.value = target.value;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(
    () => void replaceListQuery({ q: search.value.trim() || undefined, page: 1 }),
    250,
  );
}

function changeState(event: Event) {
  const target = event.target;
  if (target instanceof HTMLSelectElement)
    void replaceListQuery({ state: target.value || undefined, page: 1 });
}

function changePlatform(event: Event) {
  const target = event.target;
  if (target instanceof HTMLSelectElement)
    void replaceListQuery({ platform: target.value || undefined, page: 1 });
}

function clearListFilters() {
  search.value = "";
  void replaceListQuery({ q: undefined, state: undefined, platform: undefined, page: 1 });
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
  return actions.value.find(
    (action) =>
      action.resource_ref === `campaign:${rule.pk}` &&
      action.kind === "fire_campaign",
  );
}

function fireUnavailableReason(rule: Campaign): string {
  const action = fireAction(rule);
  if (!rule.is_active || action?.reason === "campaign_inactive") {
    return "Ligue a campanha antes de preparar um disparo.";
  }
  if (!action || action.reason === "command_not_available") {
    return "O disparo direto está indisponível até concluir a atualização de segurança.";
  }
  if (action.reason === "missing_capability") {
    return "Seu perfil não autoriza disparos manuais.";
  }
  return "O disparo manual não está disponível agora.";
}

function openNew() {
  editingPk.value = null;
  creating.value = true;
}

function openEdit(rule: Campaign) {
  creating.value = false;
  editingPk.value = rule.pk;
}

function close() {
  creating.value = false;
  editingPk.value = null;
}

/** Disparar agora: a campanha manual, sem esperar evento da padaria. */
function openFire(rule: Campaign) {
  cancelFireCommand();
  fireResult.value = null;
  fireError.value = "";
  firing.value = rule;
}

function closeFire() {
  cancelFireCommand();
  fireResult.value = null;
  fireError.value = "";
  firing.value = null;
}

async function recordFireFailure(error: unknown) {
  const status = httpError(error).status;
  if (status === 409) {
    await refresh();
    const current = rules.value.find((rule) => rule.pk === firing.value?.pk);
    if (current) firing.value = current;
    fireError.value =
      "A campanha mudou em outra sessão. Recarregamos os dados; aguarde a nova contagem, confira e tente novamente.";
    return;
  }
  fireError.value = httpErrorMessage(
    error,
    status === 429
      ? "O limite temporário de disparos foi atingido. Aguarde o prazo indicado e tente novamente; nada foi criado."
      : "Não foi possível preparar o disparo. Nada foi criado.",
  );
}

async function showFireResult(response: MarketingCommandResponse) {
  fireResult.value = response;
  fireError.value = "";
  await refresh();
}

async function onFire(request: {
  audience: ChosenAudience;
  sku: string;
  productLabel: string;
}) {
  if (!firing.value) return;
  const action = fireAction(firing.value);
  if (!action) {
    fireError.value = "A ação segura de disparo não está disponível. Atualize a lista.";
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
  const ok = editing.value
    ? await patch(editing.value.pk, payload)
    : await create(payload);
  busy.value = false;
  if (ok) {
    close();
    await nextTick();
    clearBrowserMarketingDraft({ owner: draftOwner.value, resource });
  }
}

useHead({ title: "Campanhas · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex flex-wrap items-center gap-3">
      <h1 class="w-full text-xl font-bold sm:w-auto">Campanhas</h1>
      <!-- A biblioteca de modelos é vista SECUNDÁRIA daqui, não seção irmã: o gestor pensa
           "o que a padaria diz quando X acontece", e separar o texto da intenção o obrigava
           a montar isso em duas telas. -->
      <NuxtLink
        to="/templates"
        class="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted sm:ml-auto"
      >
        <Icon name="lucide:file-text" class="size-3.5" />
        Modelos
      </NuxtLink>
      <button
        type="button"
        class="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Nova campanha
      </button>
    </div>

    <div
      v-if="error && rules.length === 0"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">
        Não conseguimos carregar as campanhas.
      </p>
      <button
        type="button"
        class="mt-1 underline underline-offset-2"
        @click="refresh()"
      >
        Tentar de novo
      </button>
    </div>

    <div
      v-else-if="loading && rules.length === 0"
      class="space-y-3"
      aria-busy="true"
    >
      <div
        v-for="n in 3"
        :key="n"
        class="h-20 animate-pulse rounded-xl bg-muted"
      ></div>
    </div>

    <div
      v-else-if="rules.length === 0"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:sliders-horizontal"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">Nenhuma campanha ainda</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Uma campanha liga um evento da padaria a um anúncio. Comece pela
        fornada.
      </p>
      <button
        type="button"
        class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        @click="openNew"
      >
        <Icon name="lucide:plus" class="size-4" />
        Criar a primeira
      </button>
    </div>

    <template v-else>
      <section
        class="mb-4 rounded-xl border border-border bg-card p-3"
        aria-labelledby="campaign-filters-title"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 id="campaign-filters-title" class="text-sm font-semibold">
            Encontrar uma campanha
          </h2>
          <button
            v-if="hasListFilters"
            type="button"
            class="min-h-11 text-sm font-semibold underline underline-offset-2"
            @click="clearListFilters"
          >
            Limpar filtros
          </button>
        </div>
        <div class="mt-2 grid gap-2 sm:grid-cols-3">
          <label class="grid gap-1 text-sm font-medium">
            Buscar
            <input
              type="search"
              :value="search"
              placeholder="Nome, gatilho ou modelo"
              class="min-h-11 w-full rounded-md border border-border bg-background px-3 text-sm"
              @input="changeSearch"
            />
          </label>
          <label class="grid gap-1 text-sm font-medium">
            Situação
            <UiNativeSelect
              :value="stateFilter"
              @change="changeState"
            >
              <option value="">Todas</option>
              <option value="active">Ligadas</option>
              <option value="inactive">Desligadas</option>
            </UiNativeSelect>
          </label>
          <label class="grid gap-1 text-sm font-medium">
            Plataforma
            <UiNativeSelect
              :value="platformFilter"
              @change="changePlatform"
            >
              <option value="">Todas</option>
              <option
                v-for="platform in platforms"
                :key="platform.value"
                :value="platform.value"
              >
                {{ platform.label }}
              </option>
            </UiNativeSelect>
          </label>
        </div>
      </section>

      <div
        v-if="error"
        class="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm"
        role="status"
      >
        <p class="font-semibold">Mostrando a última lista carregada.</p>
        <p class="mt-1 text-muted-foreground">
          Não foi possível atualizar agora. Nenhuma campanha foi alterada.
        </p>
        <button
          type="button"
          class="mt-2 min-h-11 font-semibold underline underline-offset-2"
          @click="refresh()"
        >
          Tentar atualizar
        </button>
      </div>

      <div
        v-if="filteredRules.length === 0"
        class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-8 text-center"
      >
        <Icon
          name="lucide:search-x"
          class="mx-auto size-8 text-muted-foreground"
        />
        <p class="mt-2 font-semibold">Nenhuma campanha combina com os filtros</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Limpe ou ajuste os filtros para ampliar a busca.
        </p>
        <button
          type="button"
          class="mt-3 min-h-11 font-semibold underline underline-offset-2"
          @click="clearListFilters"
        >
          Limpar filtros
        </button>
      </div>

      <ul
        v-else
        class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card"
      >
      <li
        v-for="rule in pageRules"
        :key="rule.pk"
        class="grid grid-cols-[2.75rem_minmax(0,1fr)] items-start gap-x-3 gap-y-2 px-4 py-3 sm:flex sm:gap-3"
      >
        <!-- Liga/desliga: o gesto mais comum, a um toque -->
        <button
          type="button"
          role="switch"
          :aria-checked="rule.is_active"
          :aria-label="`${rule.is_active ? 'Desligar' : 'Ligar'} a campanha ${rule.name}`"
          class="-ml-2 grid size-11 shrink-0 place-items-center rounded-md"
          @click="toggle(rule)"
        >
          <span
            aria-hidden="true"
            class="flex h-5 w-9 items-center rounded-full transition-colors"
            :class="rule.is_active ? 'bg-primary' : 'bg-muted-foreground/30'"
          >
            <span
              class="size-4 rounded-full bg-white shadow transition-transform"
              :class="rule.is_active ? 'translate-x-4' : 'translate-x-0.5'"
            ></span>
          </span>
        </button>

        <button
          type="button"
          class="col-start-2 min-w-0 text-left sm:flex-1"
          @click="openEdit(rule)"
        >
          <p
            class="font-semibold"
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
              Saiu {{ formatCount(rule.sent_count) }}× · {{ formatCount(rule.reached_total) }}
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
          class="col-start-2 flex min-h-11 shrink-0 items-center justify-end gap-2 sm:min-h-0"
        >
          <span
            v-if="!rule.requires_approval"
            class="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
            title="Publica sem passar por revisão"
          >
            Automática
          </span>
          <!-- Disparar não espera o evento: fica ao lado da campanha, mas só ativo
               quando ela está ligada — disparar campanha desligada é engano. -->
          <button
            type="button"
            :disabled="!fireAction(rule)?.enabled"
            :aria-label="
              fireAction(rule)?.enabled
                ? `Disparar a campanha ${rule.name} agora`
                : `${fireUnavailableReason(rule)} Campanha ${rule.name}`
            "
            :title="
              fireAction(rule)?.enabled ? '' : fireUnavailableReason(rule)
            "
            class="inline-flex min-h-11 items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-semibold transition hover:bg-muted disabled:opacity-40 sm:min-h-0"
            @click="openFire(rule)"
          >
            <Icon name="lucide:send" class="size-3.5" />
            {{ fireAction(rule)?.enabled ? "Disparar" : "Indisponível" }}
          </button>
          <Icon
            name="lucide:chevron-right"
            class="size-4 text-muted-foreground"
          />
        </div>
      </li>
      </ul>

      <nav
        v-if="totalPages > 1"
        class="mt-4 flex items-center justify-between gap-3"
        aria-label="Páginas de campanhas"
      >
        <button
          type="button"
          class="min-h-11 rounded-md border border-border px-4 text-sm font-semibold disabled:opacity-40"
          :disabled="currentPage <= 1"
          @click="replaceListQuery({ page: currentPage - 1 })"
        >
          Anterior
        </button>
        <p class="text-sm text-muted-foreground" role="status">
          Página {{ Math.min(currentPage, totalPages) }} de {{ totalPages }} ·
          {{ filteredRules.length }} campanhas
        </p>
        <button
          type="button"
          class="min-h-11 rounded-md border border-border px-4 text-sm font-semibold disabled:opacity-40"
          :disabled="currentPage >= totalPages"
          @click="replaceListQuery({ page: currentPage + 1 })"
        >
          Próxima
        </button>
      </nav>
    </template>

    <!-- Painel lateral: edita sem tirar a lista da vista -->
    <UiSheet
      :open="panelOpen"
      @update:open="
        (v) => {
          if (!v) close();
        }
      "
    >
      <!-- Casca sem padding + regiões com o seu: o cabeçalho fica parado e só o corpo
           rola. Mesmo desenho do slide-over de produto do gestor de pedidos. -->
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{
            editing ? "Editar campanha" : "Nova campanha"
          }}</UiSheetTitle>
          <UiSheetDescription>
            Um evento da padaria vira um anúncio para as pessoas certas.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <CampaignForm
            :rule="editing"
            :triggers="triggers"
            :platform-options="platforms"
            :templates="templates"
            :offers="offers"
            :price-tiers="priceTiers"
            :tags="tags"
            :rfm-segments="rfmSegments"
            :platform-labels="platformLabels"
            :whatsapp-template="waTemplate.current.value"
            :busy="busy"
            :draft-owner="draftOwner"
            :shop-timezone="shopTimezone"
            @submit="onSubmit"
            @cancel="close"
          />
        </div>
      </UiSheetContent>
    </UiSheet>

    <!-- Disparo manual: painel próprio, para não se confundir com editar a campanha -->
    <UiSheet
      :open="firing !== null"
      @update:open="
        (v) => {
          if (!v) closeFire();
        }
      "
    >
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>Disparar agora</UiSheetTitle>
          <UiSheetDescription>
            {{ firing?.name }} — escolha o público. O texto vem do modelo e o
            anúncio nasce para revisão.
          </UiSheetDescription>
        </UiSheetHeader>
        <div class="flex-1 overflow-y-auto p-4">
          <FireCampaignPanel
            :rule="firing"
            :price-tiers="priceTiers"
            :tags="tags"
            :rfm-segments="rfmSegments"
            :products="products"
            :product-required="firingTemplateRequiresProduct"
            :busy="busy"
            :error="fireError"
            :result="fireResult"
            @submit="onFire"
            @cancel="closeFire"
          />
        </div>
      </UiSheetContent>
    </UiSheet>

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
