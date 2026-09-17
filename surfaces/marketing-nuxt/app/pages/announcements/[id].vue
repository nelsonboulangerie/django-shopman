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
import { scheduleSummary } from "~/utils/marketingSchedule";

const route = useRoute();
const pk = computed(() => Number(route.params.id));

const [legacyRequest, resultRequest] = await Promise.all([
  useFetch<{
    announcement: Announcement;
    shop_timezone: string;
    quiet_hours_suspended_for_local_simulation: boolean;
  }>(() => `/api/v1/backstage/marketing/announcements/${pk.value}/`, {
    key: () => `announcement-${pk.value}`,
    onResponseError: operatorSessionOnError,
  }),
  useFetch<MarketingEnvelopeV2>(
    () => `/api/v1/backstage/marketing/v2/announcements/${pk.value}/`,
    {
      key: () => `announcement-result-v2-${pk.value}`,
      onResponseError: operatorSessionOnError,
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
const rejectReason = ref("");
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

const OUTCOME_TONE_CLASS = {
  ok: "border-emerald-500/40 bg-emerald-500/5 text-emerald-800 dark:text-emerald-300",
  attention: "border-warning/40 bg-warning/5 text-warning",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  quiet: "border-border bg-muted/40 text-foreground",
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
    includesDirectMessage: outcome.platforms.includes("whatsapp"),
    includesPublicPublication: outcome.platforms.some(
      (platform) => platform !== "whatsapp",
    ),
    scheduledSummary: outcome.scheduledFor
      ? scheduleSummary(outcome.scheduledFor, shopTimezone.value)
      : "",
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

useHead({ title: "Anúncio" });
</script>

<template>
  <main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
    <section
      v-if="pendingReauthentication"
      class="mb-4 rounded-md border border-warning/40 bg-warning/5 p-4"
      role="status"
    >
      <p class="font-semibold">Sua sessão voltou. A decisão não foi enviada.</p>
      <p class="mt-1 text-sm text-muted-foreground">
        O rascunho e a intenção foram preservados. Retome para receber uma nova
        conferência do servidor.
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <UiButton
          type="button"
          :disabled="confirmingDecision"
          @click="resumeServerDecision"
        >
          {{ confirmingDecision ? "Retomando…" : "Retomar e reconfirmar" }}
        </UiButton>
        <UiButton
          type="button"
          variant="outline"
          :disabled="confirmingDecision"
          @click="cancelServerDecision"
        >
          Agora não
        </UiButton>
      </div>
      <p
        v-if="decisionError"
        class="mt-2 text-sm text-destructive"
        role="alert"
      >
        {{ decisionError }}
      </p>
    </section>

    <NuxtLink
      to="/"
      class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
    >
      <Icon name="lucide:arrow-left" class="size-4" />
      Voltar ao painel
    </NuxtLink>

    <!-- O que a decisão causou, em estado. Fica na tela; o toast só acompanha. -->
    <section
      v-if="decisionNotice"
      data-focus-target="decision-outcome"
      tabindex="-1"
      class="mb-4 scroll-mt-4 rounded-md border p-4 outline-none"
      :class="OUTCOME_TONE_CLASS[decisionNotice.tone]"
      role="status"
      aria-labelledby="decision-outcome-title"
    >
      <div class="flex items-start gap-2.5">
        <Icon :name="decisionNotice.icon" class="mt-0.5 size-5 shrink-0" />
        <div class="min-w-0">
          <h2 id="decision-outcome-title" class="font-semibold">
            {{ decisionNotice.title }}
          </h2>
          <p class="mt-1 text-sm opacity-90">{{ decisionNotice.detail }}</p>
          <p
            v-if="trackingDelivery"
            class="mt-2 flex items-center gap-1.5 text-sm opacity-90"
          >
            <Icon
              name="lucide:loader-circle"
              class="size-4 shrink-0 animate-spin"
            />
            Acompanhando a entrega…
          </p>
          <template v-else-if="trackingExhausted">
            <p class="mt-2 text-sm opacity-90">
              O registro de entrega ainda não respondeu. Não vamos inferir
              sucesso sem ele: pode ser só demora da fila.
            </p>
            <UiButton
              type="button"
              variant="outline"
              class="mt-2"
              @click="trackDeliveryUntilSettled"
            >
              <Icon name="lucide:refresh-cw" class="size-4" />
              Conferir de novo
            </UiButton>
          </template>
        </div>
      </div>
    </section>

    <div
      v-if="pending && !announcement"
      class="h-64 animate-pulse rounded-md bg-muted"
      aria-busy="true"
    ></div>

    <div
      v-else-if="error || !announcement"
      class="rounded-md border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:search-x"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">{{ loadFailure.title }}</p>
      <p class="mt-1 text-sm text-muted-foreground">{{ loadFailure.detail }}</p>
      <UiButton
        v-if="loadFailure.canRetry"
        type="button"
        variant="outline"
        class="mt-3"
        @click="refreshAll"
      >
        <Icon name="lucide:refresh-cw" class="size-4" />
        Tentar novamente
      </UiButton>
      <NuxtLink
        v-else
        to="/"
        class="mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium transition hover:bg-muted"
      >
        Ver o painel
      </NuxtLink>
    </div>

    <template v-else>
      <!-- Já decidido: mostra o estado em vez de oferecer botões que não valem mais -->
      <div
        v-if="announcement.status !== 'pending_review'"
        class="mb-4 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm"
      >
        <p class="font-semibold">Este anúncio já foi decidido.</p>
        <p class="mt-0.5 text-muted-foreground">
          Situação: {{ announcement.status_label
          }}<template v-if="announcement.approved_by">
            · por {{ announcement.approved_by }}</template
          >
        </p>
      </div>

      <section
        v-if="announcement.status === 'pending_review'"
        id="review"
        class="scroll-mt-4"
        aria-label="Revisão do anúncio"
      >
        <!-- Quem veio do disparo precisa saber por que está aqui — e que nada saiu. -->
        <div
          v-if="dispatchNotice"
          class="mb-3 flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm"
          role="status"
        >
          <Icon
            name="lucide:badge-check"
            class="mt-0.5 size-4 shrink-0 text-muted-foreground"
          />
          <div class="min-w-0">
            <p class="font-medium">{{ dispatchNotice.title }}</p>
            <p class="text-muted-foreground">{{ dispatchNotice.detail }}</p>
            <p v-if="dispatchNotice.replayNote" class="text-muted-foreground">
              {{ dispatchNotice.replayNote }}
            </p>
          </div>
        </div>

        <AnnouncementCard
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
          @reject="
            confirmingReject = true;
            rejectReason = '';
          "
        />
      </section>

      <article
        v-else-if="announcement.status === 'rejected'"
        class="rounded-md border border-border bg-card p-4"
      >
        <h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Texto recusado
        </h2>
        <p class="whitespace-pre-line text-sm">{{ announcement.body }}</p>
        <!-- Recusa é decisão de alguém, e a decisão precisa ser legível depois. Sem
             isto, o motivo ficaria só no banco. -->
        <p
          v-if="announcement.status === 'rejected'"
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
      </article>

      <div
        v-if="
          announcement.status !== 'pending_review' &&
          resultPending &&
          !resultAnnouncement
        "
        class="mt-4 h-48 animate-pulse rounded-md bg-muted"
        aria-busy="true"
      ></div>
      <div
        v-else-if="
          announcement.status !== 'pending_review' &&
          (resultError || !resultAnnouncement)
        "
        class="mt-4 rounded-md border border-warning/40 bg-warning/5 p-4 text-sm"
        role="alert"
      >
        <p class="font-semibold">
          O conteúdo abriu, mas o resultado de entrega não.
        </p>
        <p class="mt-1 text-muted-foreground">
          Não vamos inferir sucesso enquanto o registro de entrega não
          responder. O comprovante preservado continua abaixo quando existir.
        </p>
        <UiButton
          type="button"
          variant="link"
          class="mt-2"
          @click="refreshResult()"
        >
          Tentar carregar o resultado
        </UiButton>
      </div>
      <AnnouncementResultPanel
        v-else-if="
          announcement.status !== 'pending_review' && resultAnnouncement
        "
        class="mt-4"
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

    <UiDialog
      :open="confirmingReject"
      @update:open="(v) => (confirmingReject = v)"
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar este anúncio?</UiDialogTitle>
          <UiDialogDescription>
            Ele não vai para nenhuma plataforma e não volta para a fila.
          </UiDialogDescription>
        </UiDialogHeader>
        <div>
          <label for="reject-reason" class="mb-1 block text-xs font-medium text-muted-foreground">
            Motivo (opcional)
          </label>
          <UiInput
            id="reject-reason"
            v-model="rejectReason"
            type="text"
            :maxlength="200"
            placeholder="Foto ruim, texto errado, produto acabou…"
          />
        </div>
        <UiDialogFooter>
          <UiButton
            type="button"
            variant="outline"
            @click="confirmingReject = false"
          >
            Manter na fila
          </UiButton>
          <UiButton
            type="button"
            variant="destructive"
            @click="
              confirmingReject = false;
              decide('reject', { reason: rejectReason.trim() });
            "
          >
            Recusar
          </UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <MarketingCommandConfirmationDialog
      :command="pendingDecision"
      :busy="confirmingDecision"
      :error="decisionError"
      :shop-timezone="shopTimezone"
      @confirm="confirmServerDecision"
      @cancel="cancelServerDecision"
    />
  </main>
</template>
