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
import { reachLines } from "~/presentation/marketingDelivery";
import {
  acceptedAwaitingConfirmationNote,
  approvalCanaryNote,
  commandReceiptPresentation,
  deliveryCountItems,
  deliveryStatePresentation,
  platformFanoutSummary,
  platformResultLabel,
  platformSwitchedOff,
  platformSwitchedOffNote,
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
  approvedText?: string;
  quietHoursSuspendedForLocalSimulation?: boolean;
}>();

const emit = defineEmits<{
  receipt: [response: MarketingCommandResponse];
  refresh: [];
}>();

/** O tom do resultado na cor do aviso do conjunto mínimo. */
const RESULT_COLOR = {
  ok: "success",
  attention: "warning",
  danger: "error",
  quiet: "info",
} as const;

/** O tom de cada contagem na cor do selo. */
const COUNT_COLOR = {
  ok: "success",
  attention: "warning",
  danger: "error",
  quiet: "neutral",
} as const;

const result = computed(() =>
  deliveryStatePresentation(
    props.announcement.delivery.state,
    props.announcement.state,
  ),
);
/**
 * "aceito pelo provedor; entrega ainda não confirmada" é o estado que mais confunde:
 * o número está lá e o gestor não sabe se fez alguma coisa errada. A nota diz o que
 * acontece a seguir, e onde.
 */
const acceptedNote = computed(() =>
  acceptedAwaitingConfirmationNote(props.announcement.delivery.counts.accepted),
);
const showsPlatformResults = computed(
  () =>
    props.announcement.delivery.target_count > 0 ||
    props.announcement.delivery.fanout_expected > 0 ||
    !["rejected", "expired"].includes(props.announcement.state),
);
const recoveryActions = computed(() => props.actions.filter(isRecoveryAction));
type PlatformDelivery = AnnouncementProjectionV2["delivery"]["platforms"][number];

function isSwitchedOff(platform: PlatformDelivery): boolean {
  return platformSwitchedOff(props.announcement, platform.platform_ref);
}

function waitsForSwitch(platform: PlatformDelivery): boolean {
  return platform.counts.queued > 0 && isSwitchedOff(platform);
}

function platformCountItems(platform: PlatformDelivery) {
  return deliveryCountItems(platform.counts, {
    platformSwitchedOff: isSwitchedOff(platform),
  });
}

const waitingSwitchedOffLabels = computed(() =>
  props.announcement.delivery.platforms
    .filter(waitsForSwitch)
    .map((platform) => platformResultLabel(platform.platform_ref)),
);
const decisionNextStep = computed(() => {
  if (
    props.announcement.delivery.state === "not_started" &&
    props.announcement.scheduled_for
  ) {
    return "Aguardar o horário agendado ou cancelar antes do início.";
  }
  const available = recoveryActions.value.find((action) => action.enabled);
  if (available) return recoveryActionLabel(available);
  if (waitingSwitchedOffLabels.value.length) {
    return `Pedir à operação para ligar ${waitingSwitchedOffLabels.value.join(", ")}; até lá, nada é disparado para eles.`;
  }
  if (result.value.tone === "ok") return "Nenhuma ação necessária.";
  return "Acompanhar o resultado antes de tomar outra decisão.";
});
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
  const platformRefs = (
    Array.isArray(rawPlatforms)
      ? rawPlatforms.filter(
          (platform): platform is string => typeof platform === "string",
        )
      : props.announcement.platform_refs
  );
  const platforms = platformRefs.map(platformResultLabel);
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
    canary: approvalCanaryNote(receipt),
    platforms: platforms.join(", "),
    execution:
      mode === "scheduled" || props.announcement.scheduled_for
        ? scheduledFor
          ? `Agendada para ${scheduleSummary(scheduledFor, props.shopTimezone)}`
          : "Agendada"
        : scheduledFor
          ? `Imediata (${scheduleSummary(scheduledFor, props.shopTimezone)})`
          : "Imediata",
    timezone:
      props.shopTimezone === "America/Sao_Paulo"
        ? "Horário de São Paulo"
        : props.shopTimezone,
    deliveryWindow: platformRefs.includes("whatsapp")
      ? props.quietHoursSuspendedForLocalSimulation
        ? "Ensaio local: silêncio 20:00–08:00 suspenso, sem efeito externo."
        : "WhatsApp respeita o silêncio 20:00–08:00; o horário escolhido já foi validado."
      : "Sem janela de silêncio adicional.",
    validity: props.announcement.expires_at
      ? `Expira em ${scheduleSummary(props.announcement.expires_at, props.shopTimezone)}.`
      : "Este anúncio não expira antes do envio.",
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
const recoveryDialogPresentation = computed(() => {
  const action = activeAction.value;
  if (action?.kind === "reconcile_unknown_delivery") {
    return {
      icon: "lucide:search",
      safetyTitle: "Somente consulta: nada será reenviado",
      safetyDetail: "O sistema apenas pergunta ao provedor o que aconteceu.",
      confirmLabel: "Consultar resultado",
    };
  }
  if (action?.kind === "retry_failed_delivery") {
    return {
      icon: "lucide:refresh-cw",
      safetyTitle: "Somente as falhas recuperáveis serão repetidas",
      safetyDetail: "Aceitos, confirmados e resultados incertos ficam intocados.",
      confirmLabel: `Tentar apenas ${formatCount(action.eligible_count)} ${action.eligible_count === 1 ? "falha" : "falhas"}`,
    };
  }
  if (action?.kind === "cancel_announcement") {
    return {
      icon: "lucide:circle-x",
      safetyTitle: "Somente o trabalho ainda reversível será cancelado",
      safetyDetail: "O que já começou nunca será apresentado como desfeito.",
      confirmLabel: "Confirmar cancelamento",
    };
  }
  return {
    icon: "lucide:shield-check",
    safetyTitle: "Confira a consequência antes de autorizar",
    safetyDetail: "Se o anúncio mudar antes de você confirmar, a ação é recusada e nada é disparado.",
    confirmLabel: "Confirmar ação",
  };
});

/** O alcance do reenvio, na grandeza de cada destino — a mesma regra da caixa de
 *  confirmação, que é a peça que acertou primeiro. */
const recoveryReach = computed(() =>
  reachLines({
    platforms: challenge.value?.platforms ?? [],
    audienceCount: challenge.value?.audience_count ?? 0,
  }),
);

/** O autenticador digita casa a casa (`NuxtPinInput`); o comando leva o código inteiro. */
const credentialDigits = computed({
  get: () => credential.value.split(""),
  set: (digits: string[]) => {
    credential.value = digits.join("").replace(/\D/g, "").slice(0, 6);
  },
});

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

// Chegou pelo item dos Agendados (v4 pino 5: "reagendar, cancelar o que não começou"
// no próprio item): `?action=cancel_announcement` ou `reschedule_announcement` abre o
// mesmo gesto que o botão daqui abriria, uma vez. A ação continua sendo a que o
// servidor ofereceu: sem ela habilitada, nada abre.
const route = useRoute();
const DEEP_LINK_ACTIONS = new Set(["cancel_announcement", "reschedule_announcement"]);
let deepLinkUsed = false;
watch(
  () => props.actions,
  (actions) => {
    const wanted = typeof route.query.action === "string" ? route.query.action : "";
    if (deepLinkUsed || !DEEP_LINK_ACTIONS.has(wanted)) return;
    const action = actions.find((candidate) => candidate.kind === wanted && candidate.enabled);
    if (!action) return;
    deepLinkUsed = true;
    void startRecovery(action);
  },
  { immediate: true },
);

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
    <!-- O estado da entrega: aviso do conjunto mínimo, na cor do que aconteceu. -->
    <NuxtAlert
      :color="RESULT_COLOR[result.tone]"
      variant="subtle"
      :icon="result.icon"
      role="status"
      data-delivery-result
    >
      <template #title>
        <h2 id="delivery-result-heading" class="font-semibold">
          {{ result.label }}
        </h2>
      </template>
      <template #description>
        <p>{{ result.detail }}</p>
        <p
          v-if="announcement.delivery.freshness.as_of"
          class="mt-1.5 text-xs"
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
        <p v-if="acceptedNote" class="mt-2">
          {{ acceptedNote }}
        </p>
      </template>
    </NuxtAlert>

    <NuxtCard
      v-if="receipt && receiptSummary"
      as="section"
      aria-labelledby="command-receipt-heading"
      data-command-receipt
    >
      <div class="flex items-start gap-2.5">
        <Icon
          name="lucide:receipt-text"
          class="mt-0.5 size-5 shrink-0 text-muted-foreground"
        />
        <div class="min-w-0 flex-1">
          <h2 id="command-receipt-heading" class="font-semibold">
            {{ approvalEvidence ? "Resumo da decisão" : receiptSummary.title }}
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            {{
              approvalEvidence
                ? "Tudo o que foi autorizado e o estado atual estão reunidos aqui."
                : receiptSummary.detail
            }}
          </p>
          <dl
            v-if="approvalEvidence"
            class="mt-3 grid overflow-hidden rounded-md border border-border text-sm sm:grid-cols-2"
          >
            <div class="border-b border-border p-3 sm:col-span-2">
              <dt class="text-xs font-medium text-muted-foreground">
                Texto aprovado
              </dt>
              <dd class="mt-1 whitespace-pre-line font-medium">
                {{ approvedText || "Texto aprovado preservado no anúncio." }}
              </dd>
            </div>
            <div class="border-b border-border p-3 sm:border-r">
              <dt class="text-xs font-medium text-muted-foreground">Versão</dt>
              <dd class="mt-1 font-semibold">
                {{ receipt.resulting_version ?? "não informada" }}
              </dd>
            </div>
            <div class="border-b border-border p-3">
              <dt class="text-xs font-medium text-muted-foreground">Público</dt>
              <dd class="mt-1 font-semibold">{{ approvalEvidence.audience }}</dd>
              <dd
                v-if="approvalEvidence.canary"
                class="mt-1 text-xs text-muted-foreground"
              >
                {{ approvalEvidence.canary }}
              </dd>
            </div>
            <div class="border-b border-border p-3 sm:border-r">
              <dt class="text-xs font-medium text-muted-foreground">Plataformas</dt>
              <dd class="mt-1 font-semibold">{{ approvalEvidence.platforms }}</dd>
            </div>
            <div class="border-b border-border p-3">
              <dt class="text-xs font-medium text-muted-foreground">Horário</dt>
              <dd class="mt-1 font-semibold">{{ approvalEvidence.execution }}</dd>
            </div>
            <div class="border-b border-border p-3 sm:border-b-0 sm:border-r">
              <dt class="text-xs font-medium text-muted-foreground">
                Estado da entrega
              </dt>
              <dd class="mt-1 font-semibold">{{ result.label }}</dd>
            </div>
            <div class="p-3">
              <dt class="text-xs font-medium text-muted-foreground">
                Próxima ação
              </dt>
              <dd class="mt-1 font-semibold">{{ decisionNextStep }}</dd>
            </div>
            <div class="border-t border-border p-3 sm:col-span-2">
              <dt class="text-xs font-medium text-muted-foreground">
                Fuso e horário permitido
              </dt>
              <dd class="mt-1 font-semibold">
                {{ approvalEvidence.timezone }} · {{ approvalEvidence.deliveryWindow }}
              </dd>
              <dt class="mt-2 text-xs font-medium text-muted-foreground">
                Validade
              </dt>
              <dd class="mt-1 font-semibold">{{ approvalEvidence.validity }}</dd>
            </div>
          </dl>
          <dl v-else class="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            <div>
              <dt class="inline text-muted-foreground">Versão resultante:</dt>
              <dd class="inline font-semibold">
                {{ receipt.resulting_version ?? "não informada" }}
              </dd>
            </div>
          </dl>
          <p class="mt-1 text-xs text-muted-foreground">
            Comprovante:
            <span class="break-all font-mono">{{ receipt.ref }}</span>
            · registrado em
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
    </NuxtCard>

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
        <NuxtCard
          v-for="platform in announcement.delivery.platforms"
          :key="platform.platform_ref"
          as="li"
          :data-platform-result="platform.platform_ref"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="font-semibold">
              {{ platformResultLabel(platform.platform_ref) }}
            </h3>
            <!-- ⚠️ A fração só quer dizer alguma coisa quando o denominador é gente.
                 No mural ela era sempre "1/1 destinos preparados", e mandava o gestor
                 procurar o sentido de "destino" onde só há um mural. -->
            <span class="text-xs text-muted-foreground">
              {{ platformFanoutSummary(platform) }}
            </span>
          </div>
          <ul class="mt-2 flex flex-wrap gap-1.5">
            <li v-for="item in platformCountItems(platform)" :key="item.key">
              <NuxtBadge :color="COUNT_COLOR[item.tone]">
                <strong>{{ formatCount(item.count) }}</strong> {{ item.label }}
              </NuxtBadge>
            </li>
          </ul>
          <p v-if="waitsForSwitch(platform)" class="mt-2 text-xs text-warning">
            {{ platformSwitchedOffNote(platform.platform_ref) }}
          </p>
        </NuxtCard>
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
        <NuxtCard v-for="action in recoveryActions" :key="action.ref" as="li">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
            <!-- ⚠️ O rótulo mora no BOTÃO, e só lá. Impresso também aqui, a tela lia
                 "Consultar 2 resultados incertos" duas vezes na mesma linha, e a
                 explicação, que é o que o gestor precisa para decidir, virava a
                 letra miúda de um eco. -->
            <p class="min-w-0 flex-1 text-sm">
              {{
                action.enabled
                  ? recoveryActionExplanation(action)
                  : recoveryDisabledReason(action.reason)
              }}
            </p>
            <NuxtButton
              class="shrink-0"
              :color="action.kind === 'cancel_announcement' ? 'error' : 'primary'"
              :variant="action.kind === 'cancel_announcement' ? 'outline' : 'solid'"
              :label="recoveryActionLabel(action)"
              :disabled="!action.enabled || pending"
              @click="startRecovery(action)"
            />
          </div>
        </NuxtCard>
      </ul>
    </section>

    <NuxtModal
      :open="dialogOpen"
      :title="activeAction ? recoveryActionLabel(activeAction) : 'Confirmar recuperação'"
      description="Confira o que vai ser feito antes de autorizar."
      :dismissible="!pending"
      @update:open="closeDialog"
    >
      <template #body>
        <div class="space-y-4" data-recovery-dialog>
          <NuxtFormField
            v-if="activeAction?.kind === 'cancel_announcement' && !challenge"
            label="Motivo do cancelamento"
            description="Este motivo fica registrado para a equipe entender o que aconteceu."
          >
            <NuxtTextarea
              id="recovery-cancel-reason"
              v-model="reason"
              :rows="3"
              :maxlength="500"
              autofocus
              class="w-full"
              placeholder="Ex.: horário alterado ou conteúdo precisa de revisão"
            />
          </NuxtFormField>

          <p
            v-if="pending && !challenge"
            class="flex items-center gap-2 text-sm"
            aria-live="polite"
          >
            <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
            Conferindo versão, autorização e consequência…
          </p>

          <template v-else-if="challenge">
            <NuxtAlert
              color="info"
              variant="subtle"
              :icon="recoveryDialogPresentation.icon"
              :title="recoveryDialogPresentation.safetyTitle"
              :description="recoveryDialogPresentation.safetyDetail"
            />

            <!-- ⚠️ Este é o diálogo onde o gestor autoriza REENVIO, e era o que ainda
                 chamava postagem de "destino": um número só, e "37 destinos" tanto podia
                 ser 37 pessoas quanto um mural repetido 37 vezes. A caixa de confirmação
                 irmã já contava certo; a mesma regra agora mora na camada de apresentação
                 e as duas leem dela. -->
            <NuxtCard variant="soft">
              <dl class="text-center">
                <dt class="text-xs text-muted-foreground">O que isto alcança</dt>
                <dd class="mt-1 space-y-0.5 text-sm font-semibold">
                  <p v-for="line in recoveryReach" :key="line">{{ line }}</p>
                  <p v-if="!recoveryReach.length" class="text-muted-foreground">
                    Nenhuma plataforma
                  </p>
                </dd>
              </dl>
            </NuxtCard>

            <!-- ⚠️ `dual_control` deixa o botão de confirmar morto PARA SEMPRE nesta
                 caixa. O texto antigo explicava o desenho do gate e não dizia o gesto:
                 botão apagado com frase que não resolve é o mesmo que botão apagado sem
                 frase. Esta termina no que fazer. -->
            <NuxtAlert
              v-if="challenge.dual_control"
              color="warning"
              variant="subtle"
              role="alert"
              title="Este disparo precisa de duas pessoas."
              description="Você já fez a sua parte. Peça a outra pessoa com acesso ao Marketing para abrir este mesmo anúncio e confirmar. Nada é disparado até lá."
            />

            <NuxtFormField v-if="challenge.typed_phrase" label="Digite exatamente esta frase">
              <p id="recovery-typed-phrase" class="mb-1.5">
                <code class="rounded bg-muted px-1.5 py-0.5 text-sm">{{ challenge.typed_phrase }}</code>
              </p>
              <NuxtTextarea
                id="recovery-typed-confirmation"
                v-model="typedConfirmation"
                aria-describedby="recovery-typed-phrase"
                name="typed_confirmation"
                :rows="1"
                autocomplete="off"
                spellcheck="false"
                class="w-full font-mono"
              />
            </NuxtFormField>

            <template v-if="challenge.step_up !== 'none'">
              <NuxtFormField v-if="challenge.step_up === 'password'" label="Usuário">
                <NuxtInput
                  id="recovery-username"
                  name="username"
                  :model-value="operatorUsername"
                  type="text"
                  autocomplete="username"
                  readonly
                  class="w-full"
                />
              </NuxtFormField>
              <NuxtFormField v-if="challenge.step_up === 'totp'" label="Código de 6 dígitos do autenticador">
                <NuxtPinInput
                  id="recovery-credential"
                  v-model="credentialDigits"
                  :length="6"
                  otp
                  :disabled="pending"
                  @keydown.enter="confirmRecovery"
                />
              </NuxtFormField>
              <NuxtFormField v-else-if="challenge.step_up === 'password'" label="Sua senha">
                <NuxtInput
                  id="recovery-credential"
                  v-model="credential"
                  name="current_password"
                  type="password"
                  autocomplete="current-password"
                  :maxlength="200"
                  class="w-full"
                  @keyup.enter="confirmRecovery"
                />
              </NuxtFormField>
            </template>
          </template>

          <NuxtAlert
            v-if="commandError"
            color="error"
            variant="subtle"
            :title="commandError"
          />
        </div>
      </template>

      <template #footer>
        <div class="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            block
            label="Voltar sem alterar"
            :disabled="pending"
            @click="closeDialog(false)"
          />
          <NuxtButton
            v-if="activeAction?.kind === 'cancel_announcement' && !challenge"
            block
            :label="pending ? 'Conferindo…' : 'Conferir cancelamento'"
            :disabled="pending || !reason.trim()"
            @click="requestRecovery"
          />
          <!-- Com duplo controle o confirmar nunca liga, então no lugar dele vai o
               gesto que existe: fechar a caixa. -->
          <NuxtButton
            v-if="challenge && challenge.dual_control"
            block
            label="Entendi"
            @click="closeDialog(false)"
          />
          <NuxtButton
            v-else-if="challenge"
            block
            :label="pending ? 'Registrando…' : recoveryDialogPresentation.confirmLabel"
            :disabled="!confirmationReady"
            @click="confirmRecovery"
          />
          <NuxtButton
            v-else-if="
              commandError && activeAction?.kind !== 'cancel_announcement'
            "
            block
            label="Tentar de novo"
            :disabled="pending || !activeAction"
            @click="requestRecovery"
          />
        </div>
      </template>
    </NuxtModal>
  </section>
</template>
