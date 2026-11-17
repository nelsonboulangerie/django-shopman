<script setup lang="ts">
// Avaliações dos clientes no iFood (módulo Review): listar, filtrar por data,
// abrir o detalhe e responder. A fonte da verdade é o iFood; a tela relê a cada
// gesto e mostra a recusa dele com a mensagem original. O Shopman não repete as
// regras do iFood (limite de página, tamanho e situação da resposta): orienta e
// deixa o iFood decidir (ver `shopman/shop/services/ifood_review.py`).
import {
  IFOOD_REVIEW_POLICY_URL,
  pageLine,
  replyLengthHint,
  statusColor,
  summaryLine,
} from "~/presentation/ifoodReviews";
import { IFOOD_CHANNEL_REF } from "~/presentation/ifoodStore";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
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

const idToOpen = ref("");
const replyText = ref("");
const minChars = computed(() => list.value?.reply_min_chars ?? 10);
const maxChars = computed(() => list.value?.reply_max_chars ?? 300);
const hint = computed(() =>
  replyLengthHint(replyText.value, minChars.value, maxChars.value),
);
const sheetOpen = computed(() => Boolean(detailId.value));
const summaryText = computed(() => summaryLine(summary.value));

onMounted(() => {
  if (!supported) return;
  void reviews.load();
  void reviews.loadSummary();
});

function openReview(id: string) {
  replyText.value = "";
  void reviews.open(id);
}

async function sendReply() {
  if (await reviews.reply(replyText.value)) replyText.value = "";
}

useHead({ title: "Avaliações do iFood" });
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <OperatorPageHeader title="iFood · Avaliações" :filters-wrap="false">
      <template #lead>
        <NuxtButton
          to="/feeds"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Canais"
        />
      </template>
    </OperatorPageHeader>

    <div v-if="!supported" class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        icon="i-lucide-message-square-off"
        title="Este canal não tem avaliações para ler aqui"
        description="As avaliações dos clientes vêm do iFood."
        :actions="[{ label: 'Voltar para Canais', to: '/feeds', color: 'neutral', variant: 'outline' }]"
      />
    </div>

    <div v-else class="min-h-0 min-w-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <div class="max-w-4xl space-y-1 text-sm">
        <p class="text-muted-foreground">
          O que os clientes do iFood disseram dos pedidos. Avaliação com nota de 1 a 4
          e comentário fica 5 dias aguardando resposta; depois o iFood publica, com ou
          sem a resposta da loja.
        </p>
        <NuxtLink
          :to="list?.policy_url || IFOOD_REVIEW_POLICY_URL"
          target="_blank"
          external
          class="inline-flex items-center gap-1 font-medium text-primary underline"
          data-review-policy
        >
          Política de Avaliações do iFood
          <NuxtIcon name="i-lucide-external-link" class="size-3.5" />
        </NuxtLink>
        <p v-if="summaryText" class="font-semibold" data-review-summary>
          {{ summaryText }}
        </p>
      </div>

      <NuxtCard variant="soft" class="max-w-4xl">
        <form class="flex flex-wrap items-end gap-3" @submit.prevent="reviews.search()">
          <NuxtFormField label="De">
            <NuxtInput v-model="dateFrom" type="date" data-review-date-from />
          </NuxtFormField>
          <NuxtFormField label="Até">
            <NuxtInput v-model="dateTo" type="date" data-review-date-to />
          </NuxtFormField>
          <NuxtFormField
            label="Por página"
            :hint="`O iFood aceita até ${list?.ifood_max_page_size ?? 50}`"
          >
            <NuxtInput
              v-model.number="pageSize"
              type="number"
              min="1"
              max="100"
              class="w-28"
              data-review-page-size
            />
          </NuxtFormField>
          <NuxtButton type="submit" label="Buscar" icon="i-lucide-search" :loading="loading" />
        </form>
        <NuxtSeparator class="my-3" />
        <form class="flex flex-wrap items-end gap-3" @submit.prevent="openReview(idToOpen)">
          <NuxtFormField label="Abrir avaliação pelo ID" class="min-w-72 flex-1">
            <NuxtInput
              v-model="idToOpen"
              placeholder="00000000-0000-0000-0000-000000000000"
              class="w-full font-mono"
              data-review-open-id
            />
          </NuxtFormField>
          <NuxtButton
            type="submit"
            label="Abrir"
            color="neutral"
            variant="outline"
            :disabled="!idToOpen.trim()"
          />
        </form>
      </NuxtCard>

      <NuxtAlert
        v-if="listError"
        class="max-w-4xl"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :title="listError.title"
        :description="listError.ifood || undefined"
        data-review-list-error
      />

      <NuxtAlert
        v-if="list && !list.enabled"
        class="max-w-4xl"
        color="neutral"
        variant="subtle"
        icon="i-lucide-plug-zap"
        title="A integração com o iFood não está configurada neste ambiente"
      />

      <NuxtSkeleton v-if="loading && !list" class="h-40 w-full max-w-4xl" />

      <template v-if="list?.enabled && !listError">
        <p class="text-sm text-muted-foreground" data-review-page>
          {{ pageLine(list.page, list.page_count, list.total) }}
        </p>
        <NuxtEmpty
          v-if="!list.reviews.length"
          icon="i-lucide-message-square"
          title="Nenhuma avaliação no período"
          description="As avaliações aparecem no iFood de 24 a 48 horas depois do pedido."
        />
        <ul v-else class="max-w-4xl space-y-2" data-review-list>
          <li v-for="review in list.reviews" :key="review.id">
            <NuxtCard>
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0 flex-1 space-y-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-base font-semibold">
                      <NuxtIcon name="i-lucide-star" class="size-4 align-[-2px] text-warning" />
                      {{ review.score_display || "Sem nota" }}
                    </span>
                    <NuxtBadge
                      :color="statusColor(review.status)"
                      variant="subtle"
                      :label="review.status_label"
                    />
                    <span class="text-sm text-muted-foreground">
                      {{ review.created_at_display }}
                    </span>
                  </div>
                  <p v-if="review.comment" class="text-sm">{{ review.comment }}</p>
                  <p v-else class="text-sm text-muted-foreground">Sem comentário</p>
                  <dl class="grid grid-cols-[auto_1fr] gap-x-3 text-xs text-muted-foreground">
                    <dt>Pedido</dt>
                    <dd>{{ review.order_short_id ? `#${review.order_short_id}` : "-" }}</dd>
                    <dt>Visibilidade</dt>
                    <dd>{{ review.visibility_label }} ({{ review.visibility }})</dd>
                    <dt>Situação</dt>
                    <dd>{{ review.status }}</dd>
                    <dt>Versão</dt>
                    <dd>{{ review.version }}</dd>
                    <dt>Respostas</dt>
                    <dd>{{ review.replies.length }}</dd>
                    <dt>ID</dt>
                    <dd class="break-all font-mono">{{ review.id }}</dd>
                  </dl>
                </div>
                <NuxtButton
                  :label="review.can_reply ? 'Abrir e responder' : 'Abrir'"
                  :color="review.can_reply ? 'primary' : 'neutral'"
                  :variant="review.can_reply ? 'solid' : 'outline'"
                  @click="openReview(review.id)"
                />
              </div>
            </NuxtCard>
          </li>
        </ul>
        <NuxtPagination
          v-if="(list.page_count ?? 0) > 1"
          :page="list.page"
          :total="list.total ?? 0"
          :items-per-page="list.page_size"
          @update:page="reviews.goTo"
        />
      </template>
    </div>

    <NuxtSlideover
      :open="sheetOpen"
      title="Avaliação do iFood"
      :description="detailId"
      side="right"
      class="sm:max-w-xl"
      @update:open="(value: boolean) => (value ? null : reviews.close())"
    >
      <template #body>
        <div class="flex flex-col gap-4" data-review-detail>
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
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-lg font-semibold">
                <NuxtIcon name="i-lucide-star" class="size-5 align-[-3px] text-warning" />
                {{ detail.score_display || "Sem nota" }}
              </span>
              <NuxtBadge
                :color="statusColor(detail.status)"
                variant="subtle"
                :label="detail.status_label"
              />
            </div>
            <p v-if="detail.comment">{{ detail.comment }}</p>
            <p v-else class="text-muted-foreground">Sem comentário</p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt class="text-muted-foreground">Cliente</dt>
              <dd>{{ detail.customer_name || "-" }}</dd>
              <dt class="text-muted-foreground">Avaliada em</dt>
              <dd>{{ detail.created_at_display || "-" }}</dd>
              <dt class="text-muted-foreground">Pedido</dt>
              <dd>
                {{ detail.order_short_id ? `#${detail.order_short_id}` : "-" }}
                <span v-if="detail.order_created_at_display" class="text-muted-foreground">
                  · feito em {{ detail.order_created_at_display }}
                </span>
              </dd>
              <dt class="text-muted-foreground">Situação</dt>
              <dd>{{ detail.status_label }} ({{ detail.status }})</dd>
              <dt class="text-muted-foreground">Visibilidade</dt>
              <dd>{{ detail.visibility_label }} ({{ detail.visibility }})</dd>
              <template v-if="detail.score_changed && detail.previous_score !== null">
                <dt class="text-muted-foreground">Nota anterior</dt>
                <dd>{{ detail.previous_score }}</dd>
              </template>
              <dt class="text-muted-foreground">Versão</dt>
              <dd>{{ detail.version }}</dd>
              <dt class="text-muted-foreground">ID</dt>
              <dd class="break-all font-mono text-xs">{{ detail.id }}</dd>
              <dt class="text-muted-foreground">ID do pedido</dt>
              <dd class="break-all font-mono text-xs">{{ detail.order_id || "-" }}</dd>
              <dt class="text-muted-foreground">Questionário</dt>
              <dd class="break-all font-mono text-xs">{{ detail.survey_id || "-" }}</dd>
            </dl>

            <section v-if="detail.questions.length" class="space-y-2">
              <h3 class="text-sm font-semibold">Respostas do cliente ao questionário</h3>
              <ul class="space-y-1 text-sm">
                <li
                  v-for="(question, i) in detail.questions"
                  :key="i"
                  class="flex flex-wrap gap-x-1.5"
                >
                  <span class="text-muted-foreground">{{ question.title }}</span>
                  <span class="font-medium">{{ question.answers.join(", ") || "Sem resposta" }}</span>
                </li>
              </ul>
            </section>

            <section class="space-y-2">
              <h3 class="text-sm font-semibold">
                Respostas ({{ detail.replies.length }})
              </h3>
              <p v-if="!detail.replies.length" class="text-sm text-muted-foreground">
                Ninguém respondeu ainda.
              </p>
              <ul v-else class="space-y-2">
                <li
                  v-for="(item, i) in detail.replies"
                  :key="i"
                  class="rounded-md border border-default p-2 text-sm"
                >
                  <p class="text-xs text-muted-foreground">
                    {{ item.author_label }} ({{ item.author }}) · {{ item.created_at_display }}
                  </p>
                  <p>{{ item.text }}</p>
                </li>
              </ul>
            </section>

            <NuxtSeparator />

            <form class="space-y-2" data-review-reply @submit.prevent="sendReply">
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
                :class="hint.outside ? 'text-warning' : 'text-muted-foreground'"
                data-review-reply-count
              >
                {{ hint.label }}
              </p>
              <p v-if="!detail.can_reply && !replyDone" class="text-xs text-warning">
                O iFood só aceita resposta em avaliação aguardando resposta. Esta está
                {{ detail.status_label.toLowerCase() }}.
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
            </form>
          </template>
        </div>
      </template>
    </NuxtSlideover>
  </main>
</template>
