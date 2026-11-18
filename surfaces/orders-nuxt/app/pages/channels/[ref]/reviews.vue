<script setup lang="ts">
// Avaliações dos clientes no iFood (módulo Review). Três abas, com a aba na query
// (`?tab=all`): "Aguardando resposta" é a fila de quem responde (com o prazo no
// cartão), "Respondidas" mostra o que espera a reação do cliente, e "Todas" é a
// lista paginada do iFood. A fonte da verdade é o iFood; a tela relê a cada gesto
// e mostra a recusa dele em português, com a mensagem original em letra pequena.
// O Shopman não repete as regras do iFood (limite de página, tamanho e situação da
// resposta): orienta e deixa o iFood decidir (`shopman/shop/services/ifood_review.py`).
import {
  emptyTitle,
  IFOOD_REVIEW_POLICY_URL,
  pageLine,
  REVIEW_TABS,
  replyLengthHint,
  reviewTabFromQuery,
  statusColor,
  summaryLine,
  type ReviewTab,
} from "~/presentation/ifoodReviews";
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const router = useRouter();
const channel = String(route.params.ref);
const supported = channel === IFOOD_CHANNEL_REF;

const reviews = useIFoodReviews();
const {
  pageSize,
  dateFrom,
  dateTo,
  list,
  listError,
  loading,
  summary,
  detail,
  detailId,
  detailError,
  detailLoading,
  replying,
  replyError,
  replyDone,
} = reviews;

const tab = computed<ReviewTab>({
  get: () => reviewTabFromQuery(route.query.tab),
  set: (value) =>
    void router.replace({
      query: { ...route.query, tab: value === "waiting" ? undefined : value },
    }),
});
const tabItems = REVIEW_TABS.map((t) => ({ label: t.label, value: t.value }));
watch(
  tab,
  (value) => {
    reviews.status.value = REVIEW_TABS.find((t) => t.value === value)?.status ?? "";
    reviews.page.value = 1;
    if (supported && import.meta.client) void reviews.load();
  },
  { immediate: true },
);

const replyText = ref("");
const minChars = computed(() => list.value?.reply_min_chars ?? 10);
const maxChars = computed(() => list.value?.reply_max_chars ?? 300);
const ifoodMaxPage = computed(() => list.value?.ifood_max_page_size ?? 50);
const hint = computed(() =>
  replyLengthHint(replyText.value, minChars.value, maxChars.value),
);
const sheetOpen = computed(() => Boolean(detailId.value));
const summaryText = computed(() => summaryLine(summary.value));

onMounted(() => {
  if (!supported) return;
  void reviews.loadSummary();
  if (!list.value && !loading.value) void reviews.load();
});

function openReview(id: string) {
  replyText.value = "";
  void reviews.open(id);
}

async function sendReply() {
  if (await reviews.reply(replyText.value)) replyText.value = "";
}

// "Abrir pelo ID": ferramenta de conferência, mora no ⋮ do cabeçalho.
const idDialogOpen = ref(false);
const idToOpen = ref("");
function openById() {
  const id = idToOpen.value.trim();
  if (!id) return;
  idDialogOpen.value = false;
  openReview(id);
}
const moreItems = computed(() => [
  {
    label: "Abrir avaliação pelo ID",
    icon: "i-lucide-search-code",
    onSelect: () => {
      idToOpen.value = "";
      idDialogOpen.value = true;
    },
  },
  {
    label: "Política de Avaliações do iFood",
    icon: "i-lucide-external-link",
    to: list.value?.policy_url || IFOOD_REVIEW_POLICY_URL,
    target: "_blank",
  },
]);

const copiedKey = ref("");
function copy(key: string, value: string) {
  void navigator.clipboard
    .writeText(value)
    .then(() => {
      copiedKey.value = key;
      setTimeout(() => (copiedKey.value = ""), 2000);
    })
    .catch(() => (copiedKey.value = ""));
}
const ifoodData = computed(() =>
  detail.value
    ? [
        { key: "id", label: "ID da avaliação", value: detail.value.id, copy: true },
        { key: "order", label: "ID do pedido no iFood", value: detail.value.order_id, copy: true },
        { key: "survey", label: "ID do questionário", value: detail.value.survey_id, copy: true },
        { key: "status", label: "Situação", value: detail.value.status, copy: false },
        { key: "visibility", label: "Visibilidade", value: detail.value.visibility, copy: false },
        { key: "version", label: "Versão", value: detail.value.version, copy: false },
      ].filter((row) => row.value)
    : [],
);

useHead({ title: "Avaliações do iFood" });
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <OperatorPageHeader title="Avaliações do iFood" :filters-wrap="false">
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
        <span v-if="summaryText" class="truncate text-xs text-muted" data-review-summary>
          {{ summaryText }}
        </span>
      </template>
      <template #filters>
        <NuxtForm
          :state="{ dateFrom, dateTo }"
          class="flex items-end gap-2"
          @submit="reviews.search()"
        >
          <NuxtFormField label="De" size="sm">
            <UiDateField v-model="dateFrom" label="Avaliações desde" data-review-date-from />
          </NuxtFormField>
          <NuxtFormField label="Até" size="sm">
            <UiDateField v-model="dateTo" label="Avaliações até" data-review-date-to />
          </NuxtFormField>
          <NuxtButton
            type="submit"
            label="Filtrar"
            icon="i-lucide-calendar-search"
            color="neutral"
            variant="outline"
            :loading="loading"
            data-review-filter
          />
        </NuxtForm>
      </template>
      <template #more>
        <OperatorMoreMenu :items="moreItems" label="Mais ações das avaliações" data-review-more />
      </template>
    </OperatorPageHeader>

    <div class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        v-if="!supported"
        icon="i-lucide-message-square-off"
        title="Este canal não tem avaliações para ler aqui"
        description="As avaliações dos clientes vêm do iFood."
        :actions="[{ label: 'Voltar para Canais', to: '/feeds', color: 'neutral', variant: 'outline' }]"
      />

      <div v-else class="flex max-w-4xl flex-col gap-4">
        <p class="text-sm text-muted">
          Avaliação com nota de 1 a 4 e comentário fica 5 dias aguardando resposta;
          depois o iFood publica, com ou sem a resposta da loja.
          <NuxtLink
            :to="list?.policy_url || IFOOD_REVIEW_POLICY_URL"
            target="_blank"
            external
            class="font-medium text-primary underline"
            data-review-policy
          >Política de Avaliações do iFood</NuxtLink>
        </p>

        <NuxtTabs
          v-model="tab"
          :items="tabItems"
          :content="false"
          variant="link"
          aria-label="Avaliações por situação"
          data-review-tabs
        />

        <NuxtAlert
          v-if="listError"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :title="listError.title"
          :description="listError.ifood || undefined"
          data-review-list-error
        />
        <NuxtAlert
          v-else-if="list && !list.enabled"
          color="info"
          variant="subtle"
          icon="i-lucide-plug-zap"
          title="A integração com o iFood não está configurada neste ambiente"
        />
        <NuxtSkeleton v-else-if="loading && !list" class="h-40 w-full" />

        <template v-if="list?.enabled && !listError">
          <NuxtAlert
            v-if="list.truncated"
            color="warning"
            variant="subtle"
            icon="i-lucide-filter"
            title="O período é longo e a lista parou antes do fim"
            description="Escolha um período menor para ver todas."
          />
          <NuxtEmpty
            v-if="!list.reviews.length"
            icon="i-lucide-message-square"
            :title="emptyTitle(tab)"
            description="As avaliações aparecem no iFood de 24 a 48 horas depois do pedido."
          />
          <ul v-else class="flex flex-col gap-2" data-review-list>
            <li v-for="review in list.reviews" :key="review.id">
              <NuxtCard>
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0 flex-1 space-y-1.5">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="inline-flex items-center gap-1 text-base font-semibold">
                        <NuxtIcon name="i-lucide-star" class="size-4 text-warning" />
                        {{ review.score_display || "Sem nota" }}
                      </span>
                      <NuxtBadge
                        :color="statusColor(review.status)"
                        :label="review.status_label"
                      />
                      <span class="text-sm text-muted">{{ review.created_at_display }}</span>
                    </div>
                    <p v-if="review.comment">{{ review.comment }}</p>
                    <p v-else class="text-muted">Sem comentário</p>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                      <NuxtLink
                        v-if="review.order_ref"
                        :to="`/${encodeURIComponent(review.order_ref)}`"
                        class="font-medium text-primary underline"
                        data-review-order-link
                      >Pedido {{ review.order_short_id ? `#${review.order_short_id}` : review.order_ref }}</NuxtLink>
                      <span v-else-if="review.order_short_id" class="text-muted">
                        Pedido #{{ review.order_short_id }}
                      </span>
                      <span
                        v-if="review.reply_by_display"
                        class="font-medium text-warning"
                        data-review-reply-by
                      >Responder até {{ review.reply_by_display }}</span>
                    </div>
                  </div>
                  <NuxtButton
                    :label="review.can_reply ? 'Responder' : 'Ver avaliação'"
                    :color="review.can_reply ? 'primary' : 'neutral'"
                    :variant="review.can_reply ? 'solid' : 'outline'"
                    data-review-open
                    @click="openReview(review.id)"
                  />
                </div>
              </NuxtCard>
            </li>
          </ul>
        </template>

        <div
          v-if="tab === 'all' && (list?.enabled || listError)"
          class="flex flex-wrap items-end justify-between gap-3"
          data-review-pager
        >
          <p class="text-sm text-muted" data-review-page>
            {{ list && !listError ? pageLine(list.page, list.page_count, list.total) : "" }}
          </p>
          <div class="flex flex-wrap items-end gap-3">
            <NuxtForm
              :state="{ pageSize }"
              class="flex items-end gap-2"
              @submit="reviews.search()"
            >
              <NuxtFormField :label="`Por página (máximo do iFood: ${ifoodMaxPage})`" size="sm">
                <NuxtInput
                  v-model.number="pageSize"
                  type="number"
                  min="1"
                  max="100"
                  size="sm"
                  class="w-24"
                  data-review-page-size
                />
              </NuxtFormField>
              <NuxtButton
                type="submit"
                label="Aplicar"
                color="neutral"
                variant="outline"
                data-review-page-apply
              />
            </NuxtForm>
            <NuxtPagination
              v-if="list && !listError && (list.page_count ?? 0) > 1"
              :page="list.page"
              :total="list.total ?? 0"
              :items-per-page="list.page_size"
              @update:page="reviews.goTo"
            />
          </div>
        </div>
      </div>
    </div>

    <NuxtModal
      v-model:open="idDialogOpen"
      title="Abrir avaliação pelo ID"
      description="O ID é o código da avaliação no iFood."
    >
      <template #body>
        <NuxtForm :state="{ idToOpen }" class="flex flex-col gap-3" @submit="openById">
          <NuxtFormField label="ID da avaliação">
            <NuxtInput
              v-model="idToOpen"
              placeholder="00000000-0000-0000-0000-000000000000"
              class="w-full font-mono"
              autofocus
              data-review-open-id
            />
          </NuxtFormField>
          <NuxtButton
            type="submit"
            label="Abrir"
            class="self-end"
            :disabled="!idToOpen.trim()"
            data-review-open-id-submit
          />
        </NuxtForm>
      </template>
    </NuxtModal>

    <NuxtSlideover
      :open="sheetOpen"
      title="Avaliação do iFood"
      side="right"
      class="sm:max-w-xl"
      @update:open="(value: boolean) => (value ? null : reviews.close())"
    >
      <template #body>
        <div class="flex flex-col gap-5" data-review-detail>
          <NuxtSkeleton v-if="detailLoading" class="h-40 w-full" />
          <NuxtAlert
            v-if="detailError"
            color="error"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            :title="detailError.title"
            :description="detailError.ifood || undefined"
              data-review-detail-error
          />
          <template v-if="detail">
            <section class="space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center gap-1 text-lg font-semibold">
                  <NuxtIcon name="i-lucide-star" class="size-5 text-warning" />
                  {{ detail.score_display || "Sem nota" }}
                </span>
                <NuxtBadge
                  :color="statusColor(detail.status)"
                  :label="detail.status_label"
                />
                <span
                  v-if="detail.reply_by_display"
                  class="text-sm font-medium text-warning"
                >Responder até {{ detail.reply_by_display }}</span>
              </div>
              <p v-if="detail.comment" class="text-base">{{ detail.comment }}</p>
              <p v-else class="text-muted">Sem comentário</p>
            </section>

            <dl class="grid grid-cols-[minmax(0,8rem)_1fr] gap-x-3 gap-y-1.5 text-sm">
              <dt class="text-muted">Cliente</dt>
              <dd>{{ detail.customer_name || "Não informado" }}</dd>
              <dt class="text-muted">Avaliada em</dt>
              <dd>{{ detail.created_at_display || "Não informado" }}</dd>
              <dt class="text-muted">Pedido</dt>
              <dd>
                <NuxtLink
                  v-if="detail.order_ref"
                  :to="`/${encodeURIComponent(detail.order_ref)}`"
                  class="font-medium text-primary underline"
                >{{ detail.order_short_id ? `#${detail.order_short_id}` : detail.order_ref }}</NuxtLink>
                <span v-else>{{ detail.order_short_id ? `#${detail.order_short_id}` : "Não informado" }}</span>
                <span v-if="detail.order_created_at_display" class="text-muted">
                  · feito em {{ detail.order_created_at_display }}
                </span>
              </dd>
              <dt class="text-muted">Visível para</dt>
              <dd>{{ detail.visibility === "PRIVATE" ? "Só a loja" : "Todos no iFood" }}</dd>
            </dl>

            <section v-if="detail.questions.length" class="space-y-2">
              <h3 class="text-sm font-semibold">O que o cliente marcou</h3>
              <dl class="space-y-2 text-sm">
                <div v-for="(question, i) in detail.questions" :key="i">
                  <dt class="text-muted">{{ question.title }}</dt>
                  <dd class="font-medium">{{ question.answers.join(", ") || "Sem resposta" }}</dd>
                </div>
              </dl>
            </section>

            <section v-if="detail.replies.length" class="space-y-2">
              <h3 class="text-sm font-semibold">Conversa</h3>
              <ul class="space-y-2">
                <li
                  v-for="(item, i) in detail.replies"
                  :key="i"
                  class="rounded-md border border-default p-3 text-sm"
                >
                  <p class="text-xs text-muted">
                    {{ item.author_label }} · {{ item.created_at_display }}
                  </p>
                  <p>{{ item.text }}</p>
                </li>
              </ul>
            </section>

            <NuxtForm
              :state="{ replyText }"
              class="space-y-2"
              data-review-reply
              @submit="sendReply"
            >
              <NuxtFormField label="Responder ao cliente">
                <NuxtTextarea
                  v-model="replyText"
                  :rows="4"
                  autoresize
                  class="w-full"
                  data-review-reply-text
                />
              </NuxtFormField>
              <p
                class="text-xs"
                :class="hint.outside ? 'text-warning' : 'text-muted'"
                data-review-reply-count
              >
                {{ hint.label }}
              </p>
              <p
                v-if="!detail.can_reply && !replyError && !replyDone"
                class="text-xs text-muted"
              >
                O iFood só aceita resposta enquanto a avaliação aguarda resposta.
              </p>
              <NuxtAlert
                v-if="replyError"
                color="error"
                variant="subtle"
                icon="i-lucide-triangle-alert"
                :title="replyError.title"
                :description="replyError.ifood || undefined"
                      data-review-reply-error
              />
              <NuxtAlert
                v-if="replyDone"
                color="success"
                variant="subtle"
                icon="i-lucide-check"
                :title="replyDone"
              />
              <NuxtButton
                type="submit"
                label="Enviar resposta ao iFood"
                icon="i-lucide-send"
                :loading="replying"
              />
            </NuxtForm>

            <NuxtCollapsible class="border-t border-default pt-3">
              <NuxtButton
                label="Dados do iFood"
                icon="i-lucide-database"
                trailing-icon="i-lucide-chevron-down"
                color="neutral"
                variant="ghost"
                data-review-ifood-data-toggle
              />
              <template #content>
                <dl class="mt-2 space-y-1.5 text-sm" data-review-ifood-data>
                  <div
                    v-for="row in ifoodData"
                    :key="row.key"
                    class="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-x-2"
                  >
                    <dt class="text-muted">{{ row.label }}</dt>
                    <dd class="min-w-0 break-all font-mono text-xs">{{ row.value }}</dd>
                    <NuxtButton
                      v-if="row.copy"
                      :icon="copiedKey === row.key ? 'i-lucide-check' : 'i-lucide-copy'"
                      :aria-label="copiedKey === row.key ? 'Copiado' : `Copiar ${row.label}`"
                      color="neutral"
                      variant="ghost"
                      size="xs"
                      square
                      @click="copy(row.key, row.value)"
                    />
                    <span v-else />
                  </div>
                </dl>
              </template>
            </NuxtCollapsible>
          </template>
        </div>
      </template>
    </NuxtSlideover>
  </main>
</template>
