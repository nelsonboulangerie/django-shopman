<script setup lang="ts">
// Um announcement, sozinho na tela — destino do link da notificação acionável
// (``UserNotification.action_url`` = /campaign/announcements/<pk>/).
//
// O gestor recebe o aviso no celular, toca e cai direto na decisão. Mesmo card
// do painel: uma única forma de decidir, um único lugar para acertar.
import { buildApprovalCommand } from "~/composables/useCampaignBoard";
import type {
  Announcement,
  AnnouncementEdits,
  MarketingCommandReceipt,
  MarketingCommandResponse,
  MarketingEnvelopeV2,
  PublishMode,
} from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";
import {
  preserveMarketingReceipt,
  restoreMarketingReceipt,
} from "~/utils/marketingReceipt";
import {
  announcementDispatchNotice,
  decisionOutcomeNotice,
  deliverySettled,
  marketingLoadError,
  DELIVERY_TRACKING_POLICY,
} from "~/presentation/marketingResult";
// Um dono só para "WhatsApp fala com pessoa, o resto é mural": o card da revisão e a
// caixa de confirmação já liam daqui, e escrever a regra pela terceira vez seria pedir
// que as três envelhecessem separadas.
import {
  includesDirectMessage,
  includesPublicPost,
  outgoingImageUrl,
} from "~/presentation/marketingDelivery";
import { scheduleSummary } from "~/utils/marketingSchedule";
import { clockLabel, decisionTitle, remainingLabel } from "~/presentation/decisions";
import type { DecisionItem } from "~/types/decisions";
import type { OperatorActionBarAction } from "../../../../operator-kit/app/presentation/actionBar";
import type { OperatorHeaderAction } from "../../../../operator-kit/app/presentation/pageHeader";

const route = useRoute();
const pk = computed(() => Number(route.params.id));

const [legacyRequest, resultRequest] = await Promise.all([
  useFetch<{
    announcement: Announcement;
    shop_timezone: string;
    quiet_hours_suspended_for_local_simulation: boolean;
  }>(() => `/api/v1/backstage/marketing/announcements/${pk.value}/`, {
    key: () => `announcement-${pk.value}`,
    onResponseError: marketingSessionOnError,
  }),
  useFetch<MarketingEnvelopeV2>(
    () => `/api/v1/backstage/marketing/v2/announcements/${pk.value}/`,
    {
      key: () => `announcement-result-v2-${pk.value}`,
      onResponseError: marketingSessionOnError,
    },
  ),
]);
const { data, refresh, pending, error } = legacyRequest;
const {
  data: resultEnvelope,
  refresh: refreshResult,
  pending: resultPending,
  error: resultError,
} = resultRequest;
const { platforms, products, shopTimezone: optionsTimezone } = useCampaigns();
// Prontidão por plataforma: o card conta ANTES de aprovar onde o anúncio não sai.
const { platforms: platformReadiness } = usePlatforms();

const announcement = computed(() => data.value?.announcement);
const shopTimezone = computed(
  () => data.value?.shop_timezone || optionsTimezone.value,
);
const quietHoursSuspendedForLocalSimulation = computed(
  () => data.value?.quiet_hours_suspended_for_local_simulation ?? false,
);
const resultAnnouncement = computed(() =>
  resultEnvelope.value?.data.kind === "announcement_detail"
    ? resultEnvelope.value.data.announcement
    : null,
);
const resultActions = computed(() => resultEnvelope.value?.actions ?? []);
const loadFailure = computed(() => marketingLoadError(error.value));
const currentReceipt = ref<MarketingCommandReceipt | null>(null);
const serverReceipt = computed<MarketingCommandReceipt | null>(() =>
  resultEnvelope.value?.data.kind === "announcement_detail"
    ? resultEnvelope.value.data.latest_receipt
    : null,
);
const displayedReceipt = computed(() => {
  const browserReceipt = currentReceipt.value;
  const durableReceipt = serverReceipt.value;
  if (!browserReceipt) return durableReceipt;
  if (!durableReceipt) return browserReceipt;
  return Date.parse(durableReceipt.created_at) >=
    Date.parse(browserReceipt.created_at)
    ? durableReceipt
    : browserReceipt;
});
const decisionCommand = useMarketingDecisionCommand();
const pendingDecision = decisionCommand.pendingDecision;
const pendingReauthentication = decisionCommand.pendingReauthentication;
const decisionError = ref("");
const confirmingDecision = ref(false);
const busy = ref(false);
const confirmingReject = ref(false);
const approvalKeys = new Map<string, string>();
const draftOwner = useMarketingDraftOwner();
// Foco explícito: esta tela não é uma sequência de blocos, mas o estado que nasce de
// uma decisão precisa chegar aos olhos de quem estava rolando no meio da página.
const { reveal } = useNextFocus();

onMounted(() => {
  currentReceipt.value = restoreMarketingReceipt(pk.value);
});

/**
 * Chegou por um disparo? O `dispatch` na query diz isso — e só isso. Os números vêm do
 * comprovante e das plataformas do próprio anúncio, nunca da URL.
 */
const dispatchNotice = computed(() => {
  const mode = route.query.dispatch;
  if (mode !== "new" && mode !== "replayed") return null;
  const rawCount = displayedReceipt.value?.outcome.audience_count;
  return announcementDispatchNotice({
    platforms: announcement.value?.platforms ?? [],
    audienceCount:
      typeof rawCount === "number" && Number.isFinite(rawCount) ? rawCount : 0,
    replayed: mode === "replayed",
  });
});

/** O tom do que a decisão causou, na cor do aviso do conjunto mínimo. */
const OUTCOME_COLOR = {
  ok: "success",
  attention: "warning",
  danger: "error",
  quiet: "info",
} as const;

/**
 * O que a última decisão causou — estado, não toast.
 *
 * O toast some enquanto a entrega ainda está acontecendo, e foi isso que deixou o
 * gestor sem saber se disparou. Esta faixa fica.
 */
const decisionOutcome = ref<{
  action: "approve" | "reject";
  publishMode?: PublishMode;
  platforms: string[];
  scheduledFor: string;
} | null>(null);
const decisionNotice = computed(() => {
  const outcome = decisionOutcome.value;
  if (!outcome) return null;
  return decisionOutcomeNotice({
    action: outcome.action,
    publishMode: outcome.publishMode,
    includesDirectMessage: includesDirectMessage(outcome.platforms),
    includesPublicPost: includesPublicPost(outcome.platforms),
    scheduledSummary: outcome.scheduledFor
      ? scheduleSummary(outcome.scheduledFor, shopTimezone.value)
      : "",
    // O mesmo estado que encerra o acompanhamento é o que deixa a faixa trocar o
    // gerúndio pelo particípio. Enquanto não assentar, "Enviado" seria mentira.
    settled: deliverySettled(resultAnnouncement.value?.delivery),
  });
});

/**
 * Acompanhamento da entrega — não há canal SSE de marketing, e abrir um é WP próprio.
 *
 * A directive roda depois da decisão: no instante do refresh o resultado ainda é
 * indefinido, e foi esse vazio que o gestor leu como "não aconteceu nada". Então a tela
 * pergunta de novo, com espera crescente, até o estado assentar — e PARA. Se o teto
 * chegar sem resposta, a tela diz isso e oferece o gesto; sucesso não se infere.
 */
class DeliveryNotSettled extends Error {}

const trackingDelivery = ref(false);
const trackingExhausted = ref(false);
let trackingToken = 0;

async function trackDeliveryUntilSettled() {
  const token = ++trackingToken;
  trackingDelivery.value = true;
  trackingExhausted.value = false;
  try {
    await retryWithBackoff(
      async () => {
        if (token !== trackingToken) return;
        await refreshResult();
        if (!deliverySettled(resultAnnouncement.value?.delivery)) {
          throw new DeliveryNotSettled();
        }
      },
      {
        ...DELIVERY_TRACKING_POLICY,
        // Só "ainda não assentou" merece nova pergunta. Falha de rede sai pelo teto,
        // que já termina dizendo que não sabemos — nunca dizendo que deu certo.
        shouldRetry: (error) =>
          error instanceof DeliveryNotSettled && token === trackingToken,
        // Um navegador, um gestor: jitter aqui só atrasaria a resposta.
        jitter: () => 0,
      },
    );
  } catch {
    if (token === trackingToken) trackingExhausted.value = true;
  } finally {
    if (token === trackingToken) trackingDelivery.value = false;
  }
}

// Desmontou a tela, acabou o acompanhamento: nada fica batendo no servidor.
onBeforeUnmount(() => {
  trackingToken += 1;
});

async function refreshAll() {
  await Promise.all([refresh(), refreshResult()]);
}

function rememberReceipt(response: MarketingCommandResponse) {
  currentReceipt.value = response.receipt;
  preserveMarketingReceipt(pk.value, response.receipt);
  if (data.value) {
    data.value = { ...data.value, announcement: response.announcement };
  }
}

async function decide(
  action: "approve" | "reject",
  body: AnnouncementEdits | { reason: string } = {},
  publishMode?: PublishMode,
) {
  busy.value = true;
  decisionError.value = "";
  try {
    const commandBody =
      action === "approve"
        ? buildApprovalCommand(
            body as AnnouncementEdits,
            announcement.value!.version,
            publishMode!,
            shopTimezone.value,
          )
        : { ...body, base_version: announcement.value?.version };
    const fingerprint = `${action}:${pk.value}:${JSON.stringify(commandBody)}`;
    let idempotencyKey = approvalKeys.get(fingerprint);
    if (!idempotencyKey) {
      idempotencyKey = globalThis.crypto.randomUUID();
      approvalKeys.set(fingerprint, idempotencyKey);
    }
    const response = await decisionCommand.begin({
      announcementId: pk.value,
      action,
      body: commandBody,
      idempotencyKey,
    });
    if (response) await finishDecision(response, action, publishMode);
  } catch (err) {
    useSonner.error(
      httpErrorMessage(err, "Não foi possível concluir. Tente de novo."),
    );
    await refreshAll();
  } finally {
    busy.value = false;
  }
}

async function finishDecision(
  response: MarketingCommandResponse,
  action: "approve" | "reject",
  publishMode?: PublishMode,
) {
  rememberReceipt(response);
  decisionOutcome.value = {
    action,
    publishMode,
    platforms: response.announcement.platforms ?? [],
    scheduledFor: response.announcement.scheduled_for || "",
  };
  useSonner.success(
    action === "reject"
      ? "Anúncio recusado."
      : publishMode === "scheduled"
        ? "Anúncio agendado."
        : "Entrega autorizada agora.",
  );
  clearBrowserMarketingDraft({
    owner: draftOwner.value,
    resource: `announcement:${pk.value}`,
  });
  // Stay on the exact resource: the receipt and per-platform result are the
  // useful completion state, not a toast followed by a generic board.
  await refreshAll();
  await nextTick();
  reveal("decision-outcome");
  // Entrega imediata é a única que ainda vai mexer sozinha; agendada e recusa já
  // assentaram, e perguntar de novo seria ruído. Sem `await`: o acompanhamento leva
  // dezenas de segundos, e prender o diálogo e o card nesse tempo seria trocar um
  // silêncio por uma trava.
  if (action === "approve" && publishMode !== "scheduled") {
    void trackDeliveryUntilSettled();
  }
}

async function confirmServerDecision(value: {
  credential: string;
  typedConfirmation: string;
  deviceSealed?: boolean;
  secondApproved?: boolean;
}) {
  const command = decisionCommand.pendingDecision.value;
  if (!command) return;
  confirmingDecision.value = true;
  decisionError.value = "";
  try {
    const response = await decisionCommand.confirm(value);
    await finishDecision(
      response,
      command.action,
      command.body.publish_mode as PublishMode | undefined,
    );
  } catch (err) {
    decisionError.value = httpErrorMessage(
      err,
      "Não foi possível confirmar. O anúncio continua sem nova decisão.",
    );
  } finally {
    confirmingDecision.value = false;
  }
}

function cancelServerDecision() {
  decisionError.value = "";
  decisionCommand.cancel();
}

async function resumeServerDecision() {
  const command = pendingReauthentication.value;
  if (!command) return;
  confirmingDecision.value = true;
  decisionError.value = "";
  try {
    const response = await decisionCommand.resumeAfterReauthentication();
    if (response) {
      await finishDecision(
        response,
        command.action,
        command.body.publish_mode as PublishMode | undefined,
      );
    }
  } catch (err) {
    decisionError.value = httpErrorMessage(
      err,
      "Não foi possível retomar. Sua decisão continua preservada.",
    );
  } finally {
    confirmingDecision.value = false;
  }
}

// O título da tela é a ocasião com o produto (v4: "Lote pronto: Croissant"), o mesmo
// do cartão da fila; sem ocasião, o nome da campanha; sem campanha, anúncio avulso.
const headerTitle = computed(() => {
  const current = announcement.value;
  if (!current) return "Anúncio";
  const product = current.sku
    ? products.value.find((option) => option.value === current.sku)?.label || ""
    : "";
  return decisionTitle({
    trigger: current.trigger,
    product_name: product,
    campaign_name: current.rule_name,
  } as DecisionItem);
});

// O prazo, colado no título (v4: "decide até 10:15 · faltam 11 min"), no tom da
// atenção ao tempo: âmbar, mais forte quando está perto. Vermelho é de bloqueio.
const clock = ref(Date.now());
let clockTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  clockTimer = setInterval(() => (clock.value = Date.now()), 30_000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});
const deadline = computed(() => {
  const current = announcement.value;
  if (!current?.expires_at || current.status !== "pending_review") return null;
  const left = Date.parse(current.expires_at) - clock.value;
  const at = clockLabel(current.expires_at, shopTimezone.value, clock.value);
  const remaining = remainingLabel(current.expires_at, clock.value);
  return {
    clock: at,
    remaining,
    text: `decide até ${at} · ${remaining}`,
    tone: left <= 15 * 60_000 ? "font-semibold text-warning" : left <= 60 * 60_000 ? "text-warning" : "text-muted-foreground",
  };
});

// A decisão mora na página (fase 2): o cartão expõe o estado e os gestos, e a página
// monta a ação na base (abaixo de `lg`) e os dois botões da barra do topo (na mesa).
const card = ref<{
  openScheduling: () => void;
  askToReject: () => void;
  continueDecision: () => void;
  canContinue: boolean;
  continueBlockedReason: string;
} | null>(null);
const decisionOpen = computed(
  () => announcement.value?.status === "pending_review",
);
const canContinue = computed(() => Boolean(card.value?.canContinue) && !busy.value);
const continueReason = computed(() => card.value?.continueBlockedReason ?? "");
const continueAction = computed<OperatorActionBarAction>(() => ({
  label: "Continuar",
  icon: "i-lucide-arrow-right",
  loading: busy.value,
  disabled: !canContinue.value,
  reason: continueReason.value,
  onSelect: () => card.value?.continueDecision(),
}));
const rejectAction = computed<OperatorActionBarAction>(() => ({
  label: "Recusar",
  disabled: busy.value,
  onSelect: () => card.value?.askToReject(),
}));

// O ⋯ da revisão: o que não é a decisão (recusar com motivo também está no polegar).
const headerActions = computed<OperatorHeaderAction[]>(() => [
  ...(decisionOpen.value
    ? [
        {
          label: "Agendar para outra hora",
          icon: "i-lucide-calendar-clock",
          onSelect: () => card.value?.openScheduling(),
        },
        {
          label: "Recusar com motivo",
          icon: "i-lucide-circle-slash",
          onSelect: () => card.value?.askToReject(),
        },
      ]
    : []),
  { label: "Ver as campanhas", icon: "i-lucide-megaphone", to: "/settings/campaigns" },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refreshAll() },
]);

useHead({ title: "Anúncio" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- A barra do topo da revisão: o voltar no lugar do selo, o nome da ocasião, o
         prazo como estado (no celular o kit o desce para a 2ª linha) e o ⋯ com o que não
         é a decisão. Na mesa, a decisão sobe para cá (`#actions`); abaixo de `lg` ela
         mora na ação na base, no fim da página. -->
    <OperatorPageHeader
      :title="headerTitle"
      :actions="headerActions"
      actions-label="Mais ações da revisão"
    >
      <template #lead>
        <NuxtButton
          to="/"
          color="neutral"
          variant="ghost"
          square
          icon="i-lucide-arrow-left"
          aria-label="Voltar às decisões"
          title="Voltar às decisões"
          data-announcement-back
        />
      </template>
      <template v-if="deadline" #status>
        <span class="tnum text-sm" :class="deadline.tone" data-review-deadline>{{ deadline.text }}</span>
      </template>
      <template v-if="decisionOpen" #actions>
        <div class="flex items-center gap-2 max-lg:hidden" data-review-desk-actions>
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Recusar"
            :disabled="busy"
            @click="card?.askToReject()"
          />
          <NuxtButton
            trailing-icon="i-lucide-arrow-right"
            label="Continuar"
            :loading="busy"
            :disabled="!canContinue"
            :title="continueReason || undefined"
            data-testid="publish-now"
            @click="card?.continueDecision()"
          />
        </div>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-2xl flex-col gap-4">
        <NuxtAlert
          v-if="pendingReauthentication"
          color="warning"
          variant="subtle"
          icon="i-lucide-rotate-ccw"
          role="status"
          title="Sua sessão voltou. A decisão não foi enviada."
          description="Seu texto e sua escolha estão guardados. Retome para confirmar de novo."
          :actions="[
            {
              label: confirmingDecision ? 'Retomando…' : 'Retomar e reconfirmar',
              color: 'warning',
              variant: 'outline',
              loading: confirmingDecision,
              disabled: confirmingDecision,
              onClick: resumeServerDecision,
            },
            {
              label: 'Agora não',
              color: 'warning',
              variant: 'outline',
              disabled: confirmingDecision,
              onClick: cancelServerDecision,
            },
          ]"
          data-review-reauthentication
        />
        <NuxtAlert
          v-if="pendingReauthentication && decisionError"
          color="error"
          variant="subtle"
          :title="decisionError"
        />

        <!-- O que a decisão causou, em estado. Fica na tela; o toast só acompanha. -->
        <NuxtAlert
          v-if="decisionNotice"
          :color="OUTCOME_COLOR[decisionNotice.tone]"
          variant="subtle"
          :icon="decisionNotice.icon"
          :title="decisionNotice.title"
          :actions="trackingExhausted && !trackingDelivery
            ? [
              {
                label: 'Atualizar',
                icon: 'i-lucide-refresh-cw',
                color: OUTCOME_COLOR[decisionNotice.tone],
                variant: 'outline',
                onClick: trackDeliveryUntilSettled,
              },
            ]
            : []"
          role="status"
          tabindex="-1"
          class="scroll-mt-4 outline-none"
          data-focus-target="decision-outcome"
          data-decision-outcome
        >
          <template #description>
            <p>{{ decisionNotice.detail }}</p>
            <p v-if="trackingDelivery" class="mt-2 flex items-center gap-1.5">
              <Icon name="lucide:loader-circle" class="size-4 shrink-0 animate-spin" />
              Acompanhando a entrega…
            </p>
            <p v-else-if="trackingExhausted" class="mt-2">
              Ainda não sabemos se foi disparado. Provavelmente é a fila.
            </p>
          </template>
        </NuxtAlert>

        <OperatorScreenState
          v-if="pending && !announcement"
          state="loading"
          what="o anúncio"
        />

        <template v-else-if="error || !announcement">
          <OperatorScreenState
            v-if="loadFailure.canRetry"
            state="error"
            :title="loadFailure.title"
            :description="loadFailure.detail"
            @retry="refreshAll"
          />
          <OperatorScreenState
            v-else
            state="empty"
            icon="i-lucide-search-x"
            :title="loadFailure.title"
            :description="loadFailure.detail"
          >
            <template #actions>
              <NuxtButton color="neutral" variant="outline" to="/" label="Ver as decisões" />
            </template>
          </OperatorScreenState>
        </template>

        <template v-else>
          <!-- Já decidido: mostra o estado em vez de oferecer botões que não valem mais -->
          <NuxtAlert
            v-if="announcement.status !== 'pending_review'"
            color="info"
            variant="subtle"
            title="Este anúncio já foi decidido."
            :description="`Situação: ${announcement.status_label}${announcement.approved_by ? ` · por ${announcement.approved_by}` : ''}`"
            data-review-decided
          />

          <section
            v-if="announcement.status === 'pending_review'"
            id="review"
            class="flex scroll-mt-4 flex-col gap-4"
            aria-label="Revisão do anúncio"
          >
            <!-- Quem veio do disparo precisa saber por que está aqui, e que nada saiu. -->
            <NuxtAlert
              v-if="dispatchNotice"
              color="info"
              variant="subtle"
              icon="i-lucide-badge-check"
              role="status"
              :title="dispatchNotice.title"
            >
              <template #description>
                <p>{{ dispatchNotice.detail }}</p>
                <p v-if="dispatchNotice.replayNote">{{ dispatchNotice.replayNote }}</p>
              </template>
            </NuxtAlert>

            <AnnouncementCard
              ref="card"
              decision-in-page
              :announcement="announcement"
              :platform-options="platforms"
              :platform-readiness="platformReadiness"
              :product-options="products"
              :busy="busy"
              :draft-owner="draftOwner"
              :shop-timezone="shopTimezone"
              :quiet-hours-suspended-for-local-simulation="
                quietHoursSuspendedForLocalSimulation
              "
              @approve="
                (_, edits, publishMode) => decide('approve', edits, publishMode)
              "
              @reject="confirmingReject = true"
            />
          </section>

          <NuxtCard
            v-else-if="announcement.status === 'rejected'"
            as="article"
          >
            <h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Texto recusado
            </h2>
            <p class="whitespace-pre-line text-sm">{{ announcement.body }}</p>
            <!-- Recusa é decisão de alguém, e a decisão precisa ser legível depois. Sem
                 isto, o motivo ficaria só no banco. -->
            <p
              class="mt-3 flex items-start gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground"
            >
              <Icon name="lucide:circle-slash" class="mt-0.5 size-3.5 shrink-0" />
              <span>
                Recusado{{
                  announcement.rejected_by
                    ? ` por ${announcement.rejected_by}`
                    : ""
                }}<template v-if="announcement.rejected_reason"
                  >: {{ announcement.rejected_reason }}</template
                >
              </span>
            </p>
          </NuxtCard>

          <template v-if="announcement.status !== 'pending_review'">
            <OperatorScreenState
              v-if="resultPending && !resultAnnouncement"
              state="loading"
              what="o resultado da entrega"
            />
            <OperatorScreenState
              v-else-if="resultError || !resultAnnouncement"
              state="error"
              title="O conteúdo abriu, mas o resultado de entrega não."
              description="Ainda não sabemos o que foi disparado. O comprovante continua abaixo."
              @retry="refreshResult()"
            />
            <AnnouncementResultPanel
              v-else
              id="result"
              class="scroll-mt-4"
              :announcement="resultAnnouncement"
              :actions="resultActions"
              :receipt="displayedReceipt"
              :shop-timezone="shopTimezone"
              :approved-text="announcement.body"
              :quiet-hours-suspended-for-local-simulation="
                quietHoursSuspendedForLocalSimulation
              "
              @receipt="rememberReceipt"
              @refresh="refreshAll"
            />
          </template>
        </template>
      </div>
    </section>

    <!-- A decisão abaixo de `lg`: a ação na base do kit, irmã da região que rola, depois
         dela. Continuar leva ao selo (não dispara); o motivo aparece escrito quando ele
         não pode. Recusar é a segunda ação. -->
    <OperatorActionBar
      v-if="decisionOpen"
      :action="continueAction"
      :secondary="rejectAction"
      :context-label="deadline ? `Decide até ${deadline.clock}` : ''"
      :context-value="deadline?.remaining ?? ''"
      label="Decisão do anúncio"
      data-review-actions
    />

    <OperatorReasonDialog
      :open="confirmingReject"
      title="Recusar este anúncio?"
      description="Ele não vai para nenhuma plataforma e não volta para a fila."
      confirm-label="Recusar"
      reason-label="Motivo (opcional)"
      placeholder="Foto ruim, texto errado, produto acabou…"
      :maxlength="200"
      :busy="busy"
      @update:open="(open) => (confirmingReject = open)"
      @confirm="
        ({ reason }) => {
          confirmingReject = false;
          decide('reject', { reason });
        }
      "
    />

    <MarketingCommandConfirmationDialog
      :command="pendingDecision"
      :busy="confirmingDecision"
      :error="decisionError"
      :shop-timezone="shopTimezone"
      :image-url="announcement ? outgoingImageUrl(announcement) : ''"
      :platform-content="announcement?.platform_content || {}"
      @confirm="confirmServerDecision"
      @cancel="cancelServerDecision"
    />
  </main>
</template>
