<script setup lang="ts">
// Painel operacional compartilhado pelas entradas atual e V2. Manter uma única
// implementação é o primeiro gate de paridade: leitura, decisão e receipts não
// podem divergir conforme a experiência visual escolhida.
//
// Ordem deliberada: primeiro o que PEDE decisão (pendentes), depois o que já
// saiu. Números do dia por último: contexto, não protagonista.
import { outgoingImageUrl } from "~/presentation/marketingDelivery";
import {
  audienceSummary,
  announcementOutcome,
  formatCount,
  shortDateTime,
} from "~/presentation/campaign";
import type { AnnouncementEdits, PublishMode } from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";
import { preserveMarketingReceipt } from "~/utils/marketingReceipt";
import { splitByGrandeza } from "~/presentation/marketingCounters";

const props = withDefaults(defineProps<{ experience?: "current" | "v2" }>(), {
  experience: "current",
});

// Mesma leitura do histórico: sucesso PARCIAL não se disfarça de pendente.
// Se o Google saiu e o Instagram falhou, a linha precisa chamar atenção.
const OUTCOME_META = {
  published: { icon: "lucide:check-circle-2", class: "text-success" },
  partial: { icon: "lucide:alert-circle", class: "text-warning" },
  failed: { icon: "lucide:x-circle", class: "text-error" },
  pending: { icon: "lucide:clock", class: "text-muted-foreground" },
} as const;

const {
  reachLimits,
  pendingPosts,
  recentPosts,
  stats,
  freshness,
  loading,
  error,
  refresh,
  approve,
  reject,
  aiAssistAvailable,
  shopTimezone,
  quietHoursSuspendedForLocalSimulation,
  pendingDecision,
  pendingReauthentication,
  decisionError,
  confirmDecision,
  resumeDecision,
  cancelDecision,
} = useCampaignBoard();

/** Os três números que continuam somados, cada um com a linha que diz de quê.
 *
 *  Só somam porque são problemas a resolver: separar "1 pessoa sem confirmação" de
 *  "1 postagem sem confirmação" em dois cartões esconderia o menor dos dois alarmes
 *  atrás do outro. O que não pode é o total aparecer sem grandeza. */
const acceptedUnconfirmed = computed(() =>
  splitByGrandeza({
    people: stats.value?.accepted_unconfirmed_people_today ?? 0,
    posts: stats.value?.accepted_unconfirmed_posts_today ?? 0,
  }),
);
const failedFinal = computed(() =>
  splitByGrandeza({
    people: stats.value?.failed_final_people_today ?? 0,
    posts: stats.value?.failed_final_posts_today ?? 0,
  }),
);
const unknownOpen = computed(() =>
  splitByGrandeza({
    people: stats.value?.unknown_people_open ?? 0,
    posts: stats.value?.unknown_posts_open ?? 0,
  }),
);
const { platforms, products } = useCampaigns();
/** A imagem do anúncio que está na caixa de confirmação — a caixa mostra o que sai,
 *  e metade do que sai é a foto. */
const decidingPost = computed(
  () =>
    pendingPosts.value.find(
      (item) => item.pk === pendingDecision.value?.announcementId,
    ) || null,
);
const decidingImageUrl = computed(() =>
  decidingPost.value ? outgoingImageUrl(decidingPost.value) : "",
);
/** O formato público (`story`, `feed`, `standard`) mora no conteúdo por plataforma do
 *  anúncio, não no corpo editável do comando: ele não é editável no card, e é ele que
 *  decide qual retrato a prévia em tamanho real precisa mostrar. */
const decidingPlatformContent = computed(
  () => decidingPost.value?.platform_content || {},
);
// Prontidão por plataforma: o card conta ANTES de aprovar onde o anúncio não sai.
const { platforms: platformReadiness } = usePlatforms();
const busyPk = ref<number | null>(null);
const rejecting = ref<number | null>(null);
const confirmingDecision = ref(false);
const draftOwner = useMarketingDraftOwner();

async function onApprove(
  pk: number,
  edits: AnnouncementEdits,
  publishMode: PublishMode,
) {
  busyPk.value = pk;
  const response = await approve(pk, edits, publishMode);
  busyPk.value = null;
  if (response) {
    clearBrowserMarketingDraft({
      owner: draftOwner.value,
      resource: `announcement:${pk}`,
    });
    preserveMarketingReceipt(pk, response.receipt);
    await navigateTo(`/announcements/${pk}`);
  }
}

// Recusar é irreversível: o diálogo de motivo do kit confirma antes. O motivo é
// opcional de propósito (campo obrigatório aqui só produziria "não" digitado com
// pressa); quando o gestor escreve, a recusa passa a explicar a campanha.
async function confirmReject(choice: { reason: string }) {
  const pk = rejecting.value;
  if (pk === null) return;
  const reason = choice.reason.trim();
  busyPk.value = pk;
  rejecting.value = null;
  const response = await reject(pk, reason);
  busyPk.value = null;
  if (response) {
    clearBrowserMarketingDraft({
      owner: draftOwner.value,
      resource: `announcement:${pk}`,
    });
    preserveMarketingReceipt(pk, response.receipt);
    await navigateTo(`/announcements/${pk}`);
  }
}

async function confirmServerDecision(value: {
  credential: string;
  typedConfirmation: string;
}) {
  const pk = pendingDecision.value?.announcementId;
  if (!pk) return;
  confirmingDecision.value = true;
  const response = await confirmDecision(value);
  confirmingDecision.value = false;
  if (!response) return;
  clearBrowserMarketingDraft({
    owner: draftOwner.value,
    resource: `announcement:${pk}`,
  });
  preserveMarketingReceipt(pk, response.receipt);
  await navigateTo(`/announcements/${pk}`);
}

async function resumeServerDecision() {
  const pk = pendingReauthentication.value?.announcementId;
  if (!pk) return;
  confirmingDecision.value = true;
  const response = await resumeDecision();
  confirmingDecision.value = false;
  if (!response) return;
  clearBrowserMarketingDraft({
    owner: draftOwner.value,
    resource: `announcement:${pk}`,
  });
  preserveMarketingReceipt(pk, response.receipt);
  await navigateTo(`/announcements/${pk}`);
}

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
];

const freshnessTitle = computed(() => {
  if (freshness.value?.state === "stale") return "Atualização atrasada";
  if (freshness.value?.state === "degraded") return "Dados parcialmente atualizados";
  return "Situação ao vivo indisponível";
});

const REJECT_CONSEQUENCE =
  "Ele não vai para nenhuma plataforma e não volta para a fila. Nada mais muda: a campanha e o que aconteceu na padaria seguem como estão.";

useHead(() => ({
  title: props.experience === "v2" ? "Painel · V2" : "Painel",
}));
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Painel"
      :actions="headerActions"
      actions-label="Mais ações do Painel"
    />

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-4xl flex-col gap-5">
        <NuxtAlert
          v-if="pendingReauthentication"
          color="warning"
          variant="subtle"
          icon="i-lucide-log-in"
          title="Sua sessão voltou. A decisão não foi enviada."
          description="Seu texto e sua escolha estão guardados. Retome para confirmar de novo."
          :actions="[
            {
              label: confirmingDecision ? 'Retomando…' : 'Retomar e reconfirmar',
              color: 'warning',
              variant: 'outline',
              size: 'md',
              loading: confirmingDecision,
              onClick: () => void resumeServerDecision(),
            },
            {
              label: 'Agora não',
              color: 'warning',
              variant: 'outline',
              size: 'md',
              disabled: confirmingDecision,
              onClick: () => cancelDecision(),
            },
          ]"
          role="status"
        />
        <NuxtAlert
          v-if="pendingReauthentication && decisionError"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :title="decisionError"
          role="alert"
        />

        <NuxtAlert
          v-if="freshness && freshness.state !== 'fresh' && !error"
          color="warning"
          variant="subtle"
          icon="i-lucide-clock-alert"
          :title="freshnessTitle"
          description="Atualize antes de decidir pelos números abaixo. Se algo mudou, a decisão é recusada e nada é disparado."
          :actions="[
            {
              label: 'Atualizar',
              color: 'warning',
              variant: 'outline',
              size: 'md',
              onClick: () => void refresh(),
            },
          ]"
          role="status"
          aria-label="Atualidade dos dados"
        />

        <!-- Entrega por plataforma, ANTES de publicar. Bloqueio e limitação não podem
             parecer iguais: um diz "nada sai por aqui", o outro diz "sai, mas não para
             todo mundo". ⚠️ O aviso NÃO configura nada: conta o fato e aponta a casa
             (Plataformas), porque alerta não é lugar de morar configuração. -->
        <section
          v-if="reachLimits.length"
          class="flex flex-col gap-2"
          aria-label="Situação de entrega por plataforma"
        >
          <NuxtAlert
            v-for="limit in reachLimits"
            :key="limit.code"
            :color="limit.blocking ? 'error' : 'warning'"
            variant="subtle"
            :icon="limit.blocking ? 'i-lucide-circle-slash' : 'i-lucide-triangle-alert'"
            :title="limit.title"
            :actions="[
              {
                label: 'Ver em Plataformas',
                to: { path: '/settings/platforms' },
                trailingIcon: 'i-lucide-arrow-right',
                color: limit.blocking ? 'error' : 'warning',
                variant: 'outline',
                size: 'md',
              },
            ]"
            role="status"
          >
            <template #description>
              <span class="block">{{ limit.detail }}</span>
              <span v-if="limit.action" class="mt-1 block font-medium">{{ limit.action }}</span>
            </template>
          </NuxtAlert>
        </section>

        <!-- Números do dia
             ⚠️ Uma pessoa que recebe mensagem e um mural que recebe postagem são
             grandezas diferentes, e somá-las produzia um número que o gestor lê de manhã
             para decidir se disparou demais. Onde o número é bom, ele vai separado em dois
             cartões; onde o número é um problema a resolver, ele fica junto e a linha de
             baixo diz de quê: juntar dois alarmes em cartões distintos esconderia o
             menor deles. -->
        <section
          v-if="stats"
          class="grid grid-cols-2 gap-3 sm:grid-cols-3"
          aria-label="Situação operacional"
        >
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p class="text-2xl font-semibold tabular-nums">
              {{ formatCount(stats.pending_decision_count) }}
            </p>
            <p class="text-xs text-muted-foreground">Aguardando decisão</p>
          </NuxtCard>
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p class="text-2xl font-semibold tabular-nums">
              {{ formatCount(stats.confirmed_people_today) }}
            </p>
            <p class="text-xs text-muted-foreground">Pessoas que receberam hoje</p>
          </NuxtCard>
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p class="text-2xl font-semibold tabular-nums">
              {{ formatCount(stats.confirmed_posts_today) }}
            </p>
            <p class="text-xs text-muted-foreground">Postagens publicadas hoje</p>
          </NuxtCard>
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p class="text-2xl font-semibold tabular-nums">
              {{ formatCount(acceptedUnconfirmed.total) }}
            </p>
            <p class="text-xs text-muted-foreground">Sem confirmação ainda</p>
            <p class="text-xs text-muted-foreground">
              {{ acceptedUnconfirmed.breakdown }}
            </p>
          </NuxtCard>
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p
              class="text-2xl font-semibold tabular-nums"
              :class="failedFinal.total > 0 ? 'text-error' : ''"
            >
              {{ formatCount(failedFinal.total) }}
            </p>
            <p class="text-xs text-muted-foreground">Falhas finais hoje</p>
            <p class="text-xs text-muted-foreground">{{ failedFinal.breakdown }}</p>
          </NuxtCard>
          <NuxtCard class="*:data-[slot=body]:p-3">
            <p
              class="text-2xl font-semibold tabular-nums"
              :class="unknownOpen.total > 0 ? 'text-warning' : ''"
            >
              {{ formatCount(unknownOpen.total) }}
            </p>
            <p class="text-xs text-muted-foreground">Resultados incertos</p>
            <p class="text-xs text-muted-foreground">{{ unknownOpen.breakdown }}</p>
          </NuxtCard>
        </section>

        <!-- Erro de carga: o painel não finge estar vazio quando não conseguiu ler -->
        <OperatorScreenState
          v-if="error"
          state="error"
          what="o painel"
          @retry="refresh()"
        />

        <!-- Pendentes -->
        <section aria-labelledby="board-pending-title">
          <h2
            id="board-pending-title"
            class="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground"
          >
            Aguardando decisão
          </h2>

          <OperatorScreenState
            v-if="loading && pendingPosts.length === 0"
            state="loading"
            what="os anúncios"
          />

          <!-- ⚠️ Dizia "quando uma fornada terminar", e fornada é UM dos gatilhos: há
               estoque baixo, produto novo, hora marcada e o disparo na mão. Copy que
               nomeia um caso ensina o gestor a esperar só aquele. -->
          <OperatorScreenState
            v-else-if="pendingPosts.length === 0"
            state="empty"
            icon="i-lucide-coffee"
            title="Nenhum anúncio aguardando decisão."
            description="Quando uma campanha disparar, o anúncio aparece aqui para você revisar."
          >
            <template #actions>
              <NuxtButton
                to="/settings/campaigns"
                icon="i-lucide-sliders-horizontal"
                label="Ver as campanhas"
                color="neutral"
                variant="outline"
              />
            </template>
          </OperatorScreenState>

          <div v-else class="flex flex-col gap-4">
            <AnnouncementCard
              v-for="announcement in pendingPosts"
              :key="announcement.pk"
              :announcement="announcement"
              :platform-options="platforms"
              :platform-readiness="platformReadiness"
              :product-options="products"
              :busy="busyPk === announcement.pk"
              :ai-assist-available="aiAssistAvailable"
              :draft-owner="draftOwner"
              :shop-timezone="shopTimezone"
              :quiet-hours-suspended-for-local-simulation="
                quietHoursSuspendedForLocalSimulation
              "
              @approve="onApprove"
              @reject="(pk) => (rejecting = pk)"
            />
          </div>
        </section>

        <!-- Publicados nas últimas 24h -->
        <section v-if="recentPosts.length > 0" aria-labelledby="board-recent-title">
          <div class="mb-3 flex items-center gap-2">
            <h2
              id="board-recent-title"
              class="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
            >
              Últimas 24 horas
            </h2>
            <!-- A linha do tempo completa deixou de ser aba e virou aprofundamento: a
                 pergunta "o que saiu?" é fraca, e quem quer varrer clica aqui (plano §8). -->
            <NuxtButton
              to="/history"
              label="Ver tudo"
              trailing-icon="i-lucide-arrow-right"
              color="neutral"
              variant="ghost"
              class="ml-auto"
            />
          </div>
          <NuxtCard class="*:data-[slot=body]:p-0">
            <ul class="divide-y divide-border">
              <li
                v-for="announcement in recentPosts"
                :key="announcement.pk"
                class="flex items-start gap-3 px-4 py-3"
              >
                <Icon
                  :name="
                    OUTCOME_META[announcementOutcome(announcement.platform_results)]
                      .icon
                  "
                  class="mt-0.5 size-4 shrink-0"
                  :class="
                    OUTCOME_META[announcementOutcome(announcement.platform_results)]
                      .class
                  "
                  aria-hidden="true"
                />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm">{{ announcement.body }}</p>
                  <p class="mt-0.5 text-xs text-muted-foreground">
                    {{
                      shortDateTime(
                        announcement.published_at || announcement.created_at,
                      )
                    }}
                    ·
                    {{ audienceSummary(announcement.audience) }}
                  </p>
                </div>
                <NuxtButton
                  :to="`/announcements/${announcement.pk}`"
                  label="Ver resultado"
                  trailing-icon="i-lucide-arrow-right"
                  color="neutral"
                  variant="ghost"
                  class="shrink-0"
                />
              </li>
            </ul>
          </NuxtCard>
          <NuxtButton
            to="/history"
            label="Ver o histórico completo"
            trailing-icon="i-lucide-arrow-right"
            color="neutral"
            variant="ghost"
            class="mt-3"
          />
        </section>
      </div>
    </section>

    <!-- Recusar é irreversível: confirma antes, com o motivo opcional. -->
    <OperatorReasonDialog
      :open="rejecting !== null"
      title="Recusar este anúncio?"
      :description="REJECT_CONSEQUENCE"
      confirm-label="Recusar"
      reason-label="Motivo (opcional)"
      placeholder="Foto ruim, texto errado, produto acabou…"
      :maxlength="200"
      @update:open="(open) => { if (!open) rejecting = null; }"
      @confirm="confirmReject"
    />

    <MarketingCommandConfirmationDialog
      :command="pendingDecision"
      :busy="confirmingDecision"
      :error="decisionError"
      :shop-timezone="shopTimezone"
      :image-url="decidingImageUrl"
      :platform-content="decidingPlatformContent"
      @confirm="confirmServerDecision"
      @cancel="cancelDecision"
    />
  </main>
</template>
