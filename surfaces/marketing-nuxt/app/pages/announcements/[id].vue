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
import { marketingLoadError } from "~/presentation/marketingResult";

const route = useRoute();
const pk = computed(() => Number(route.params.id));

const [legacyRequest, resultRequest] = await Promise.all([
  useFetch<{ announcement: Announcement; shop_timezone: string }>(
    () => `/api/v1/backstage/marketing/announcements/${pk.value}/`,
    {
      key: () => `announcement-${pk.value}`,
      onResponseError: operatorSessionOnError,
    },
  ),
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
const { platforms, shopTimezone: optionsTimezone } = useCampaigns();

const announcement = computed(() => data.value?.announcement);
const shopTimezone = computed(
  () => data.value?.shop_timezone || optionsTimezone.value,
);
const resultAnnouncement = computed(() =>
  resultEnvelope.value?.data.kind === "announcement_detail"
    ? resultEnvelope.value.data.announcement
    : null,
);
const resultActions = computed(() => resultEnvelope.value?.actions ?? []);
const loadFailure = computed(() => marketingLoadError(error.value));
const currentReceipt = ref<MarketingCommandReceipt | null>(null);
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

onMounted(() => {
  currentReceipt.value = restoreMarketingReceipt(pk.value);
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
  useSonner.success(
    action === "reject"
      ? "Anúncio recusado."
      : publishMode === "scheduled"
        ? "Anúncio agendado."
        : "Anúncio preparado para publicação.",
  );
  clearBrowserMarketingDraft({
    owner: draftOwner.value,
    resource: `announcement:${pk.value}`,
  });
  // Stay on the exact resource: the receipt and per-platform result are the
  // useful completion state, not a toast followed by a generic board.
  await refreshAll();
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

useHead({ title: "Anúncio · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
    <section
      v-if="pendingReauthentication"
      class="mb-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4"
      role="status"
    >
      <p class="font-semibold">Sua sessão voltou. A decisão não foi enviada.</p>
      <p class="mt-1 text-sm text-muted-foreground">
        O rascunho e a intenção foram preservados. Retome para receber uma nova
        conferência do servidor.
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          class="min-h-11 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          :disabled="confirmingDecision"
          @click="resumeServerDecision"
        >
          {{ confirmingDecision ? "Retomando…" : "Retomar e reconfirmar" }}
        </button>
        <button
          type="button"
          class="min-h-11 rounded-md border border-border px-4 text-sm font-medium hover:bg-muted"
          :disabled="confirmingDecision"
          @click="cancelServerDecision"
        >
          Agora não
        </button>
      </div>
      <p v-if="decisionError" class="mt-2 text-sm text-destructive" role="alert">
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

    <div
      v-if="pending && !announcement"
      class="h-64 animate-pulse rounded-xl bg-muted"
      aria-busy="true"
    ></div>

    <div
      v-else-if="error || !announcement"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:search-x"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">{{ loadFailure.title }}</p>
      <p class="mt-1 text-sm text-muted-foreground">{{ loadFailure.detail }}</p>
      <button
        v-if="loadFailure.canRetry"
        type="button"
        class="mt-3 inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium transition hover:bg-muted"
        @click="refreshAll"
      >
        <Icon name="lucide:refresh-cw" class="size-4" />
        Tentar novamente
      </button>
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
        <p class="font-semibold">Este announcement já foi decidido.</p>
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
        <AnnouncementCard
          :announcement="announcement"
          :platform-options="platforms"
          :busy="busy"
          :draft-owner="draftOwner"
          :shop-timezone="shopTimezone"
          @approve="
            (_, edits, publishMode) => decide('approve', edits, publishMode)
          "
          @reject="
            confirmingReject = true;
            rejectReason = '';
          "
        />
      </section>

      <article v-else class="rounded-xl border border-border bg-card p-4">
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
        class="mt-4 h-48 animate-pulse rounded-xl bg-muted"
        aria-busy="true"
      ></div>
      <div
        v-else-if="
          announcement.status !== 'pending_review' &&
          (resultError || !resultAnnouncement)
        "
        class="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 text-sm"
        role="alert"
      >
        <p class="font-semibold">
          O conteúdo abriu, mas o resultado de entrega não.
        </p>
        <p class="mt-1 text-muted-foreground">
          Não vamos inferir sucesso enquanto o ledger não responder. O receipt
          preservado continua abaixo quando existir.
        </p>
        <button
          type="button"
          class="mt-2 min-h-11 font-semibold underline"
          @click="refreshResult()"
        >
          Tentar carregar o resultado
        </button>
      </div>
      <AnnouncementResultPanel
        v-else-if="
          announcement.status !== 'pending_review' && resultAnnouncement
        "
        class="mt-4"
        :announcement="resultAnnouncement"
        :actions="resultActions"
        :receipt="currentReceipt"
        :shop-timezone="shopTimezone"
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
          <label for="reject-reason" class="mb-1 block text-sm font-medium">
            Motivo (opcional)
          </label>
          <input
            id="reject-reason"
            v-model="rejectReason"
            type="text"
            maxlength="200"
            placeholder="Foto ruim, texto errado, produto acabou…"
            class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="confirmingReject = false"
          >
            Manter na fila
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="
              confirmingReject = false;
              decide('reject', { reason: rejectReason.trim() });
            "
          >
            Recusar
          </button>
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
