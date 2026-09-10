<script setup lang="ts">
import type {
  AnnouncementProjectionV2,
  MarketingActionProjectionV2,
  MarketingCommandReceipt,
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";
import {
  beginMarketingRecovery,
  confirmMarketingRecovery,
  isRecoveryAction,
} from "~/composables/useMarketingRecovery";
import { formatCount } from "~/presentation/campaign";
import {
  commandReceiptPresentation,
  deliveryCountItems,
  deliveryStatePresentation,
  platformResultLabel,
  receiptStateLabel,
  recoveryActionExplanation,
  recoveryActionLabel,
  recoveryDisabledReason,
} from "~/presentation/marketingResult";
import { scheduleSummary } from "~/utils/marketingSchedule";

const props = defineProps<{
  announcement: AnnouncementProjectionV2;
  actions: MarketingActionProjectionV2[];
  receipt?: MarketingCommandReceipt | null;
  shopTimezone: string;
}>();

const emit = defineEmits<{
  receipt: [response: MarketingCommandResponse];
  refresh: [];
}>();

const TONE_CLASS = {
  ok: "border-emerald-500/40 bg-emerald-500/5 text-emerald-800 dark:text-emerald-300",
  attention:
    "border-amber-500/40 bg-amber-500/5 text-amber-800 dark:text-amber-300",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  quiet: "border-border bg-muted/40 text-foreground",
} as const;

const COUNT_TONE_CLASS = {
  ok: "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300",
  attention: "bg-amber-500/10 text-amber-800 dark:text-amber-300",
  danger: "bg-destructive/10 text-destructive",
  quiet: "bg-muted text-muted-foreground",
} as const;

const result = computed(() =>
  deliveryStatePresentation(
    props.announcement.delivery.state,
    props.announcement.state,
  ),
);
const showsPlatformResults = computed(
  () =>
    props.announcement.delivery.target_count > 0 ||
    props.announcement.delivery.fanout_expected > 0 ||
    !["rejected", "expired"].includes(props.announcement.state),
);
const recoveryActions = computed(() => props.actions.filter(isRecoveryAction));
const receiptSummary = computed(() =>
  props.receipt ? commandReceiptPresentation(props.receipt) : null,
);
const approvalEvidence = computed(() => {
  const receipt = props.receipt;
  if (!receipt || receipt.kind !== "approve") return null;
  const rawAudience = receipt.outcome.audience_count;
  const audienceCount =
    typeof rawAudience === "number" &&
    Number.isInteger(rawAudience) &&
    rawAudience >= 0
      ? rawAudience
      : props.announcement.audience.eligible_count;
  const rawPlatforms = receipt.outcome.platforms;
  const platforms = (
    Array.isArray(rawPlatforms)
      ? rawPlatforms.filter(
          (platform): platform is string => typeof platform === "string",
        )
      : props.announcement.platform_refs
  ).map(platformResultLabel);
  const mode = receipt.outcome.publish_mode;
  const scheduledFor =
    mode === "scheduled"
      ? String(
          receipt.outcome.publish_at || props.announcement.scheduled_for || "",
        )
      : String(
          receipt.outcome.effective_at || props.announcement.approved_at || "",
        );
  return {
    audience: `${formatCount(audienceCount)} ${audienceCount === 1 ? "pessoa" : "pessoas"}`,
    platforms: platforms.join(", "),
    execution:
      mode === "scheduled" || props.announcement.scheduled_for
        ? scheduledFor
          ? `Agendada para ${scheduleSummary(scheduledFor, props.shopTimezone)}`
          : "Agendada"
        : scheduledFor
          ? `Imediata — ${scheduleSummary(scheduledFor, props.shopTimezone)}`
          : "Imediata",
  };
});

const dialogOpen = ref(false);
const activeAction = ref<MarketingActionProjectionV2 | null>(null);
const challenge = ref<MarketingConfirmationChallenge | null>(null);
const reason = ref("");
const credential = ref("");
const typedConfirmation = ref("");
const pending = ref(false);
const commandError = ref("");
const idempotencyKeys = new Map<string, string>();
const { data: operatorSession } = useNuxtData<{
  operator: { username?: string; name?: string } | null;
}>("operator-session");
const operatorUsername = computed(
  () => operatorSession.value?.operator?.username?.trim() || "",
);

const confirmationReady = computed(() => {
  const current = challenge.value;
  if (!current || current.dual_control || pending.value) return false;
  if (current.step_up === "totp" && !/^\d{6}$/.test(credential.value.trim()))
    return false;
  if (current.step_up === "password" && !credential.value) return false;
  if (
    current.typed_phrase &&
    typedConfirmation.value.trim() !== current.typed_phrase
  )
    return false;
  return true;
});

function recoveryBody(
  action: MarketingActionProjectionV2,
): Record<string, unknown> {
  return action.kind === "cancel_announcement"
    ? { reason: reason.value.trim() }
    : {};
}

function commandKey(
  action: MarketingActionProjectionV2,
  body: Record<string, unknown>,
): string {
  const fingerprint = `${action.ref}:${props.announcement.version}:${JSON.stringify(body)}`;
  let key = idempotencyKeys.get(fingerprint);
  if (!key) {
    key = globalThis.crypto.randomUUID();
    idempotencyKeys.set(fingerprint, key);
  }
  return key;
}

async function startRecovery(action: MarketingActionProjectionV2) {
  if (pending.value || !action.enabled) return;
  activeAction.value = action;
  challenge.value = null;
  reason.value = "";
  credential.value = "";
  typedConfirmation.value = "";
  commandError.value = "";
  dialogOpen.value = true;
  if (action.kind === "cancel_announcement") return;
  await requestRecovery();
}

async function requestRecovery() {
  const action = activeAction.value;
  if (!action || pending.value || !action.enabled) return;
  const body = recoveryBody(action);
  if (action.kind === "cancel_announcement" && !reason.value.trim()) return;
  pending.value = true;
  commandError.value = "";
  try {
    const started = await beginMarketingRecovery($fetch, action, {
      announcementId: announcementId(),
      baseVersion: props.announcement.version,
      idempotencyKey: commandKey(action, body),
      body,
    });
    if (started.kind === "receipt") {
      finish(started.response);
      return;
    }
    challenge.value = started.challenge;
  } catch (error) {
    flagMarketingSessionError(error);
    commandError.value = httpErrorMessage(
      error,
      "Não foi possível abrir a confirmação. O resultado continua intacto.",
    );
  } finally {
    pending.value = false;
  }
}

async function confirmRecovery() {
  const action = activeAction.value;
  const currentChallenge = challenge.value;
  if (!action || !currentChallenge || !confirmationReady.value) return;
  pending.value = true;
  commandError.value = "";
  try {
    const body = recoveryBody(action);
    const response = await confirmMarketingRecovery(
      $fetch,
      action,
      currentChallenge,
      {
        credential: credential.value,
        typedConfirmation: typedConfirmation.value,
      },
      {
        announcementId: announcementId(),
        baseVersion: props.announcement.version,
        idempotencyKey: commandKey(action, body),
        body,
      },
    );
    finish(response);
  } catch (error) {
    flagMarketingSessionError(error);
    commandError.value = httpErrorMessage(
      error,
      "Não foi possível concluir. Nenhuma recuperação foi presumida.",
    );
    const code = errorCode(error);
    if (
      [
        "version_conflict",
        "confirmation_context_changed",
        "confirmation_expired",
      ].includes(code)
    ) {
      challenge.value = null;
      emit("refresh");
    }
  } finally {
    pending.value = false;
  }
}

function finish(response: MarketingCommandResponse) {
  dialogOpen.value = false;
  challenge.value = null;
  reason.value = "";
  credential.value = "";
  typedConfirmation.value = "";
  emit("receipt", response);
  emit("refresh");
  useSonner.success(commandReceiptPresentation(response.receipt).title);
}

function announcementId(): number {
  const [, rawId = ""] = props.announcement.ref.split(":", 2);
  return Number(rawId);
}

function errorCode(error: unknown): string {
  if (typeof error !== "object" || error === null || !("data" in error))
    return "";
  return String((error as { data?: { code?: string } }).data?.code || "");
}

function closeDialog(open: boolean) {
  if (pending.value) return;
  dialogOpen.value = open;
  if (!open) {
    activeAction.value = null;
    challenge.value = null;
    reason.value = "";
    commandError.value = "";
  }
}
</script>

<template>
  <section class="space-y-4" aria-labelledby="delivery-result-heading">
    <div
      class="rounded-xl border p-4"
      :class="TONE_CLASS[result.tone]"
      role="status"
    >
      <div class="flex items-start gap-2.5">
        <Icon :name="result.icon" class="mt-0.5 size-5 shrink-0" />
        <div class="min-w-0">
          <h2 id="delivery-result-heading" class="font-semibold">
            {{ result.label }}
          </h2>
          <p class="mt-1 text-sm opacity-90">{{ result.detail }}</p>
          <p
            v-if="announcement.delivery.freshness.as_of"
            class="mt-1.5 text-xs opacity-75"
          >
            Estado consultado em
            {{
              scheduleSummary(
                announcement.delivery.freshness.as_of,
                shopTimezone,
              )
            }}
            ({{ shopTimezone }}).
          </p>
        </div>
      </div>
    </div>

    <section
      v-if="receipt && receiptSummary"
      class="rounded-xl border border-sky-500/40 bg-sky-500/5 p-4"
      aria-labelledby="command-receipt-heading"
    >
      <div class="flex items-start gap-2.5">
        <Icon
          name="lucide:receipt-text"
          class="mt-0.5 size-5 shrink-0 text-sky-700 dark:text-sky-300"
        />
        <div class="min-w-0">
          <h2 id="command-receipt-heading" class="font-semibold">
            {{ receiptSummary.title }}
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ receiptSummary.detail }}
          </p>
          <dl class="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            <div>
              <dt class="inline text-muted-foreground">Comprovante:</dt>
              <dd class="inline break-all font-mono">{{ receipt.ref }}</dd>
            </div>
            <div>
              <dt class="inline text-muted-foreground">Versão resultante:</dt>
              <dd class="inline font-semibold">
                {{ receipt.resulting_version ?? "—" }}
              </dd>
            </div>
            <template v-if="approvalEvidence">
              <div>
                <dt class="inline text-muted-foreground">
                  Público autorizado:
                </dt>
                <dd class="inline font-semibold">
                  {{ approvalEvidence.audience }}
                </dd>
              </div>
              <div>
                <dt class="inline text-muted-foreground">Plataformas:</dt>
                <dd class="inline font-semibold">
                  {{ approvalEvidence.platforms }}
                </dd>
              </div>
              <div class="sm:col-span-2">
                <dt class="inline text-muted-foreground">Execução:</dt>
                <dd class="inline font-semibold">
                  {{ approvalEvidence.execution }}
                </dd>
              </div>
            </template>
          </dl>
          <p class="mt-1 text-xs text-muted-foreground">
            Registrado em
            {{
              scheduleSummary(
                receipt.completed_at || receipt.created_at,
                shopTimezone,
              )
            }}
            ({{ shopTimezone }})<template v-if="receipt.state">
              · {{ receiptStateLabel(receipt.state) }}</template
            >
          </p>
        </div>
      </div>
    </section>

    <section
      v-if="showsPlatformResults"
      aria-labelledby="platform-results-heading"
    >
      <h2
        id="platform-results-heading"
        class="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Resultado por plataforma
      </h2>
      <ul class="mt-2 grid gap-3 sm:grid-cols-2">
        <li
          v-for="platform in announcement.delivery.platforms"
          :key="platform.platform_ref"
          class="rounded-xl border border-border bg-card p-3"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="font-semibold">
              {{ platformResultLabel(platform.platform_ref) }}
            </h3>
            <span class="text-xs text-muted-foreground">
              {{ formatCount(platform.fanout_materialized) }}/{{
                formatCount(platform.fanout_expected)
              }}
              destinos preparados
            </span>
          </div>
          <ul class="mt-2 flex flex-wrap gap-1.5">
            <li
              v-for="item in deliveryCountItems(platform.counts)"
              :key="item.key"
              class="rounded-full px-2.5 py-1 text-xs"
              :class="COUNT_TONE_CLASS[item.tone]"
            >
              <strong>{{ formatCount(item.count) }}</strong> {{ item.label }}
            </li>
          </ul>
        </li>
      </ul>
    </section>

    <section v-if="recoveryActions.length" aria-labelledby="recovery-heading">
      <h2
        id="recovery-heading"
        class="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Próximo passo
      </h2>
      <ul class="mt-2 space-y-2">
        <li
          v-for="action in recoveryActions"
          :key="action.ref"
          class="rounded-xl border border-border bg-card p-3"
        >
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium">
                {{ recoveryActionLabel(action) }}
              </p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{
                  action.enabled
                    ? recoveryActionExplanation(action)
                    : recoveryDisabledReason(action.reason)
                }}
              </p>
            </div>
            <button
              type="button"
              class="min-h-11 shrink-0 rounded-md px-3 text-sm font-semibold transition"
              :class="
                action.kind === 'cancel_announcement'
                  ? 'border border-destructive/40 text-destructive hover:bg-destructive/5'
                  : 'bg-primary text-primary-foreground hover:bg-primary/90'
              "
              :disabled="!action.enabled || pending"
              @click="startRecovery(action)"
            >
              {{ recoveryActionLabel(action) }}
            </button>
          </div>
        </li>
      </ul>
    </section>

    <UiDialog :open="dialogOpen" @update:open="closeDialog">
      <UiDialogContent class="sm:max-w-lg">
        <UiDialogHeader>
          <UiDialogTitle>
            {{
              activeAction
                ? recoveryActionLabel(activeAction)
                : "Confirmar recuperação"
            }}
          </UiDialogTitle>
          <UiDialogDescription>
            {{
              activeAction
                ? recoveryActionExplanation(activeAction)
                : "Aguarde a consequência emitida pelo servidor."
            }}
          </UiDialogDescription>
        </UiDialogHeader>

        <div v-if="activeAction?.kind === 'cancel_announcement' && !challenge">
          <label for="recovery-cancel-reason" class="block text-sm font-medium">
            Motivo do cancelamento
          </label>
          <textarea
            id="recovery-cancel-reason"
            v-model="reason"
            rows="3"
            maxlength="500"
            autofocus
            class="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            placeholder="Ex.: horário alterado ou conteúdo precisa de revisão"
          />
          <p class="mt-1 text-xs text-muted-foreground">
            Este motivo fica registrado para a equipe entender o que aconteceu.
          </p>
        </div>

        <div
          v-if="pending && !challenge"
          class="flex items-center gap-2 text-sm"
          aria-live="polite"
        >
          <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
          Conferindo versão, autorização e consequência…
        </div>

        <div v-else-if="challenge" class="space-y-4">
          <div class="rounded-lg border border-border bg-muted/50 p-3 text-sm">
            <p>
              <strong>{{ formatCount(challenge.audience_count) }}</strong>
              {{
                challenge.audience_count === 1
                  ? "destino elegível"
                  : "destinos elegíveis"
              }}
              nesta consequência.
            </p>
            <p
              v-if="challenge.platforms.length"
              class="mt-1 text-muted-foreground"
            >
              Plataformas realmente afetadas:
              {{ challenge.platforms.map(platformResultLabel).join(", ") }}.
            </p>
          </div>

          <div
            v-if="challenge.dual_control"
            class="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm"
            role="alert"
          >
            <p class="font-semibold">
              Duas pessoas são obrigatórias para este volume.
            </p>
            <p class="mt-1 text-muted-foreground">
              O comando não será executado nesta sessão sem a confirmação
              independente prevista pelo gate de segurança.
            </p>
          </div>

          <div v-if="challenge.typed_phrase">
            <label
              for="recovery-typed-confirmation"
              class="block text-sm font-medium"
            >
              Digite exatamente
              <code class="rounded bg-muted px-1.5 py-0.5">{{
                challenge.typed_phrase
              }}</code>
            </label>
            <textarea
              id="recovery-typed-confirmation"
              v-model="typedConfirmation"
              name="typed_confirmation"
              rows="1"
              autocomplete="off"
              spellcheck="false"
              class="mt-1 min-h-11 w-full resize-none rounded-md border border-border bg-background px-3 py-2.5 font-mono text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div v-if="challenge.step_up !== 'none'">
            <div v-if="challenge.step_up === 'password'" class="mb-3">
              <label for="recovery-username" class="block text-sm font-medium">
                Usuário
              </label>
              <input
                id="recovery-username"
                name="username"
                :value="operatorUsername"
                type="text"
                autocomplete="username"
                readonly
                class="mt-1 h-11 w-full rounded-md border border-border bg-muted px-3 text-sm text-muted-foreground"
              />
            </div>
            <label for="recovery-credential" class="block text-sm font-medium">
              {{
                challenge.step_up === "totp"
                  ? "Código de 6 dígitos"
                  : "Sua senha"
              }}
            </label>
            <input
              id="recovery-credential"
              v-model="credential"
              name="current_password"
              :type="challenge.step_up === 'password' ? 'password' : 'text'"
              :inputmode="challenge.step_up === 'totp' ? 'numeric' : 'text'"
              :autocomplete="
                challenge.step_up === 'totp'
                  ? 'one-time-code'
                  : 'current-password'
              "
              :maxlength="challenge.step_up === 'totp' ? 6 : 200"
              class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
              @keyup.enter="confirmRecovery"
            />
          </div>
        </div>

        <p v-if="commandError" class="text-sm text-destructive" role="alert">
          {{ commandError }}
        </p>

        <UiDialogFooter>
          <button
            type="button"
            class="min-h-11 rounded-md border border-border px-3 text-sm font-medium transition hover:bg-muted"
            :disabled="pending"
            @click="closeDialog(false)"
          >
            Voltar sem alterar
          </button>
          <button
            v-if="activeAction?.kind === 'cancel_announcement' && !challenge"
            type="button"
            class="min-h-11 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="pending || !reason.trim()"
            @click="requestRecovery"
          >
            {{ pending ? "Conferindo…" : "Conferir cancelamento" }}
          </button>
          <button
            v-if="challenge"
            type="button"
            class="min-h-11 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!confirmationReady"
            @click="confirmRecovery"
          >
            {{ pending ? "Registrando…" : "Confirmar consequência" }}
          </button>
          <button
            v-else-if="
              commandError && activeAction?.kind !== 'cancel_announcement'
            "
            type="button"
            class="min-h-11 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground"
            :disabled="pending || !activeAction"
            @click="requestRecovery"
          >
            Tentar de novo
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </section>
</template>
