<script setup lang="ts">
// O card acionável — a tela inteira do Marketing existe por causa dele.
//
// O gestor lê, ajusta o texto, confere a audiência e decide. Tudo num gesto:
// as edições viajam JUNTO com a aprovação (um request), porque salvar e depois
// publicar abriria a janela de publicar a versão anterior.
import type {
  Announcement,
  AnnouncementEdits,
  MarketingAISuggestion,
  PublishMode,
} from "~/types/campaign";
import { useMarketingDraft } from "~/composables/useMarketingDraft";
import type { MarketingDraftPayload } from "~/utils/marketingDraft";
import {
  expirySummary,
  isQuietHoursNow,
  resolveScheduleInput,
  scheduleSummary,
  suggestedScheduleLocal,
} from "~/utils/marketingSchedule";
import type { ScheduleFold } from "~/utils/marketingSchedule";
import {
  audienceSummary,
  displayHashtag,
  expiryLabel,
  expiryTone,
  parseHashtags,
  platformIcon,
  vipSummary,
} from "~/presentation/campaign";

const props = defineProps<{
  announcement: Announcement;
  platformOptions: { value: string; label: string }[];
  /** Há credencial de IA no ambiente? Sem ela o botão não aparece: oferecer e falhar
   *  depois ensina o gestor a não confiar no recurso. */
  aiAssistAvailable?: boolean;
  busy?: boolean;
  /** Stable session-owned scope. Empty disables local persistence. */
  draftOwner?: string;
  /** Named backend-owned timezone. The browser's local zone is never inferred. */
  shopTimezone?: string;
  /** Explicit server proof that this lane ends at the hermetic local simulator. */
  quietHoursSuspendedForLocalSimulation?: boolean;
}>();

const emit = defineEmits<{
  approve: [pk: number, edits: AnnouncementEdits, publishMode: PublishMode];
  reject: [pk: number];
}>();

// Rascunho local. O card é um formulário: até decidir, nada vai pro servidor.
const body = ref(props.announcement.body);
const hashtagsText = ref(
  props.announcement.hashtags.map(displayHashtag).join(" "),
);
const platforms = ref<string[]>([...props.announcement.platforms]);
const scheduling = ref(false);
const publishAt = ref("");
const publishFold = ref<ScheduleFold>("");
const rewriting = ref(false);
const assistError = ref("");
const suggestion = ref<MarketingAISuggestion | null>(null);
const suggestionUsed = ref(false);
const acceptedSuggestionRef = ref("");
const beforeSuggestion = ref<{ body: string; hashtags: string } | null>(null);
const clockMs = ref(Date.now());
let clockTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  clockTimer = setInterval(() => {
    clockMs.value = Date.now();
  }, 30_000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});

// Suggestion is shown beside the operator's text. Fetching it never mutates the draft.
async function rewrite() {
  rewriting.value = true;
  assistError.value = "";
  suggestion.value = null;
  suggestionUsed.value = false;
  acceptedSuggestionRef.value = "";
  try {
    const response = await $fetch<{ suggestion: MarketingAISuggestion }>(
      `/api/v1/backstage/marketing/announcements/${props.announcement.pk}/rewrite/`,
      {
        method: "POST",
        credentials: "same-origin",
        body: { body: body.value },
      },
    );
    suggestion.value = response.suggestion;
    beforeSuggestion.value = { body: body.value, hashtags: hashtagsText.value };
  } catch (err) {
    flagMarketingSessionError(err);
    assistError.value = httpErrorMessage(
      err,
      "O assistente não respondeu. Seu texto segue aqui.",
    );
  } finally {
    rewriting.value = false;
  }
}

function recordSuggestionDisposition(action: "accept_draft" | "discard") {
  if (!suggestion.value) return;
  void $fetch(
    `/api/v1/backstage/marketing/announcements/${props.announcement.pk}/suggestions/${suggestion.value.ref}/disposition/`,
    { method: "POST", credentials: "same-origin", body: { action } },
  ).catch((error) => {
    flagMarketingSessionError(error);
  });
}

function useSuggestion() {
  if (!suggestion.value) return;
  body.value = suggestion.value.body;
  hashtagsText.value = suggestion.value.hashtags.map(displayHashtag).join(" ");
  acceptedSuggestionRef.value = suggestion.value.ref;
  suggestionUsed.value = true;
  recordSuggestionDisposition("accept_draft");
}

function undoSuggestion() {
  if (!beforeSuggestion.value) return;
  body.value = beforeSuggestion.value.body;
  hashtagsText.value = beforeSuggestion.value.hashtags;
  acceptedSuggestionRef.value = "";
  suggestionUsed.value = false;
}

function discardSuggestion() {
  recordSuggestionDisposition("discard");
  suggestion.value = null;
  beforeSuggestion.value = null;
  acceptedSuggestionRef.value = "";
  suggestionUsed.value = false;
}

const warningLabels: Record<string, string> = {
  generic_copy: "Texto genérico: confira se combina com a ocasião.",
  limited_facts: "Poucos fatos estavam disponíveis para a sugestão.",
  operator_should_verify_tone: "Confira o tom antes de usar.",
};

// Anúncio substituído por um refetch (SSE/poll) enquanto a tela estava aberta:
// re-sincroniza o rascunho SÓ quando é outro announcement, para não apagar a edição em
// curso a cada ciclo de poll.
watch(
  () => props.announcement.pk,
  () => {
    body.value = props.announcement.body;
    hashtagsText.value = props.announcement.hashtags
      .map(displayHashtag)
      .join(" ");
    platforms.value = [...props.announcement.platforms];
    scheduling.value = false;
    publishAt.value = "";
    publishFold.value = "";
    assistError.value = "";
    suggestion.value = null;
    suggestionUsed.value = false;
    acceptedSuggestionRef.value = "";
    beforeSuggestion.value = null;
  },
);

function editorBase(): MarketingDraftPayload {
  return {
    body: props.announcement.body,
    hashtags: props.announcement.hashtags.map(displayHashtag).join(" "),
    platforms: [...props.announcement.platforms],
    scheduling: false,
    publish_at: "",
    publish_fold: "",
  };
}

function editorCurrent(): MarketingDraftPayload {
  return {
    body: body.value,
    hashtags: hashtagsText.value,
    platforms: [...platforms.value],
    scheduling: scheduling.value,
    publish_at: publishAt.value,
    publish_fold: publishFold.value,
  };
}

function applyEditorDraft(payload: MarketingDraftPayload) {
  body.value =
    typeof payload.body === "string" ? payload.body : props.announcement.body;
  hashtagsText.value =
    typeof payload.hashtags === "string"
      ? payload.hashtags
      : props.announcement.hashtags.map(displayHashtag).join(" ");
  platforms.value = Array.isArray(payload.platforms)
    ? payload.platforms.map(String)
    : [...props.announcement.platforms];
  scheduling.value = Boolean(payload.scheduling);
  publishAt.value =
    typeof payload.publish_at === "string" ? payload.publish_at : "";
  publishFold.value =
    payload.publish_fold === "earlier" || payload.publish_fold === "later"
      ? payload.publish_fold
      : "";
}

const draft = useMarketingDraft({
  owner: () => props.draftOwner ?? "",
  resource: () => `announcement:${props.announcement.pk}`,
  version: () => props.announcement.version,
  base: editorBase,
  current: editorCurrent,
  apply: applyEditorDraft,
});

const DRAFT_LABELS = {
  body: "Texto",
  hashtags: "Hashtags",
  platforms: "Plataformas",
  scheduling: "Modo de entrega",
  publish_at: "Data e hora",
  publish_fold: "Ocorrência do horário",
};

const timezoneName = computed(() => props.shopTimezone || "UTC");
const expiresAtMs = computed(() => Date.parse(props.announcement.expires_at));
const exactExpiryMinutes = computed(() => {
  if (!Number.isFinite(expiresAtMs.value))
    return props.announcement.expires_in_minutes;
  const remaining = expiresAtMs.value - clockMs.value;
  return remaining <= 0 ? 0 : Math.ceil(remaining / 60_000);
});
const expiry = computed(() =>
  props.announcement.expires_at
    ? expirySummary(
        props.announcement.expires_at,
        timezoneName.value,
        clockMs.value,
      )
    : expiryLabel(props.announcement.expires_in_minutes),
);
const expiryClass = computed(
  () =>
    ({
      urgent: "bg-destructive/10 text-destructive",
      warning: "bg-warning/10 text-warning",
      calm: "bg-muted text-muted-foreground",
      none: "",
    })[expiryTone(exactExpiryMinutes.value)],
);

const audience = computed(() => audienceSummary(props.announcement.audience));
const vip = computed(() => vipSummary(props.announcement.audience));
const platformLabels = computed<Record<string, string>>(() =>
  Object.fromEntries(
    props.platformOptions.map((option) => [option.value, option.label]),
  ),
);

const expired = computed(
  () =>
    Number.isFinite(expiresAtMs.value) && expiresAtMs.value <= clockMs.value,
);
const canPublish = computed(
  () =>
    !props.busy &&
    !expired.value &&
    body.value.trim().length > 0 &&
    platforms.value.length > 0,
);
const hasDirectMessage = computed(() => platforms.value.includes("whatsapp"));
const hasPublicPublication = computed(() =>
  platforms.value.some((platform) => platform !== "whatsapp"),
);
const deliverNowLabel = computed(() => {
  if (hasDirectMessage.value && hasPublicPublication.value)
    return "Entregar agora";
  return hasDirectMessage.value ? "Enviar agora" : "Publicar agora";
});
const nowFallsInQuietHours = computed(
  () =>
    hasDirectMessage.value &&
    !props.quietHoursSuspendedForLocalSimulation &&
    isQuietHoursNow(timezoneName.value, clockMs.value),
);
const canPublishNow = computed(
  () => canPublish.value && !nowFallsInQuietHours.value,
);
const scheduleResolution = computed(() =>
  resolveScheduleInput({
    localValue: publishAt.value,
    timeZone: timezoneName.value,
    fold: publishFold.value,
    nowMs: clockMs.value,
    expiresAt: props.announcement.expires_at,
    directMessage:
      hasDirectMessage.value && !props.quietHoursSuspendedForLocalSimulation,
  }),
);
const canSchedule = computed(
  () => canPublish.value && scheduleResolution.value.ok,
);
const schedulePreview = computed(() =>
  scheduleResolution.value.candidate
    ? scheduleSummary(
        scheduleResolution.value.candidate.instant,
        timezoneName.value,
      )
    : "",
);

function togglePlatform(value: string) {
  const index = platforms.value.indexOf(value);
  if (index >= 0) platforms.value.splice(index, 1);
  else platforms.value.push(value);
}

function edits(): AnnouncementEdits {
  return {
    body: body.value.trim(),
    hashtags: parseHashtags(hashtagsText.value),
    platforms: [...platforms.value],
    ...(acceptedSuggestionRef.value
      ? { ai_suggestion_ref: acceptedSuggestionRef.value }
      : {}),
  };
}

function publishNow() {
  if (!canPublishNow.value) return;
  draft.flush();
  emit("approve", props.announcement.pk, edits(), "now");
}

function schedule() {
  if (!canSchedule.value || !scheduleResolution.value.candidate) return;
  draft.flush();
  emit(
    "approve",
    props.announcement.pk,
    { ...edits(), publish_at: scheduleResolution.value.candidate.instant },
    "scheduled",
  );
}

function toggleScheduling() {
  scheduling.value = !scheduling.value;
  if (!scheduling.value || publishAt.value) return;
  publishAt.value = suggestedScheduleLocal({
    timeZone: timezoneName.value,
    suggestedAt: props.announcement.scheduled_for,
    nowMs: clockMs.value,
    expiresAt: props.announcement.expires_at,
  });
}

function useNextAllowedTime() {
  if (!scheduleResolution.value.nextAllowedLocal) return;
  publishAt.value = scheduleResolution.value.nextAllowedLocal;
  publishFold.value = "";
}

function askToReject() {
  draft.flush();
  emit("reject", props.announcement.pk);
}
</script>

<template>
  <article
    class="overflow-hidden rounded-md border border-border bg-card shadow-sm"
  >
    <!-- Cabeçalho: de onde veio e quanto tempo ainda vale -->
    <header
      class="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5"
    >
      <Icon name="lucide:zap" class="size-4 text-muted-foreground" />
      <span class="text-sm font-semibold">{{
        announcement.rule_name || "Anúncio avulso"
      }}</span>
      <span
        v-if="announcement.trigger_label"
        class="text-xs text-muted-foreground"
      >
        {{ announcement.trigger_label }}
      </span>
      <span
        v-if="announcement.sku"
        class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground"
      >
        {{ announcement.sku }}
      </span>
      <span
        v-if="expiry"
        class="ml-auto rounded-full px-2 py-0.5 text-xs font-semibold"
        :class="expiryClass"
      >
        {{ expiry }}
      </span>
    </header>

    <DraftRecoveryNotice
      :state="draft.state.value"
      :saved-at="draft.savedAt.value"
      :conflicts="draft.conflicts.value"
      :labels="DRAFT_LABELS"
      class="m-3 mb-0"
      @keep-local="draft.keepLocal()"
      @keep-server="draft.keepServer()"
      @discard="draft.discard()"
    />

    <div class="flex flex-col gap-4 p-4 sm:flex-row">
      <!-- Foto do produto: o announcement é visual antes de ser texto -->
      <div class="shrink-0">
        <img
          v-if="announcement.image_url"
          :src="announcement.image_url"
          :alt="`Foto de ${announcement.sku || 'produto'}`"
          class="size-32 rounded-lg border border-border object-cover"
        />
        <div
          v-else
          class="grid size-32 place-items-center rounded-lg border border-dashed border-border bg-muted/40 text-muted-foreground"
        >
          <Icon name="lucide:image-off" class="size-6" />
        </div>
      </div>

      <div class="min-w-0 flex-1 space-y-3">
        <!-- Texto editável: o template escreveu o rascunho, o gestor dá o tom -->
        <div>
          <div class="mb-1 flex items-center justify-between gap-2">
            <label
              :for="`body-${announcement.pk}`"
              class="block text-xs font-medium text-muted-foreground"
            >
              Texto do anúncio
            </label>
            <UiButton
              v-if="aiAssistAvailable && announcement.ai_suggestion_enabled"
              type="button"
              :disabled="rewriting || busy"
              variant="outline"
              size="xs"
              @click="rewrite"
            >
              <Icon
                :name="rewriting ? 'lucide:loader-circle' : 'lucide:sparkles'"
                class="size-3.5"
                :class="rewriting ? 'animate-spin' : ''"
              />
              {{ rewriting ? "Preparando…" : "Sugerir texto" }}
            </UiButton>
          </div>
          <UiTextarea
            :id="`body-${announcement.pk}`"
            v-model="body"
            name="announcement_body"
            :rows="4"
            autocomplete="off"
            class="resize-y"
          />
          <p
            v-if="!body.trim()"
            class="mt-1 text-xs text-destructive"
            role="alert"
          >
            O anúncio precisa de um texto.
          </p>
          <p
            v-if="assistError"
            class="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
            role="alert"
            data-testid="ai-assist-error"
          >
            {{ assistError }}
          </p>
          <section
            v-if="suggestion"
            class="mt-3 space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
            aria-label="Comparação da sugestão de IA"
            data-testid="ai-suggestion-compare"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p class="text-sm font-semibold">
                  Sugestão pronta para comparar
                </p>
                <p class="text-xs text-muted-foreground">
                  Usar muda só este rascunho. Nada é publicado.
                </p>
              </div>
              <span
                class="rounded-full bg-background px-2 py-1 text-[11px] text-muted-foreground"
              >
                Política {{ suggestion.policy_version }}
              </span>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <div class="rounded-md border border-border bg-background p-2">
                <p
                  class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Seu texto
                </p>
                <p class="whitespace-pre-wrap text-sm">
                  {{ beforeSuggestion?.body }}
                </p>
              </div>
              <div
                class="rounded-md border border-primary/30 bg-background p-2"
              >
                <p
                  class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-primary"
                >
                  Sugestão
                </p>
                <p class="whitespace-pre-wrap text-sm">{{ suggestion.body }}</p>
                <p
                  v-if="suggestion.hashtags.length"
                  class="mt-2 text-xs text-muted-foreground"
                >
                  {{ suggestion.hashtags.map(displayHashtag).join(" ") }}
                </p>
              </div>
            </div>
            <div v-if="suggestion.facts.length" class="text-xs">
              <p class="font-semibold">Fatos canônicos usados</p>
              <ul class="mt-1 flex flex-wrap gap-1.5">
                <li
                  v-for="fact in suggestion.facts"
                  :key="fact.id"
                  class="rounded-full border border-border bg-background px-2 py-1"
                >
                  {{ fact.label }}: {{ fact.value }}
                </li>
              </ul>
            </div>
            <ul
              v-if="suggestion.warnings.length"
              class="space-y-1 text-xs text-warning"
            >
              <li v-for="warning in suggestion.warnings" :key="warning">
                {{
                  warningLabels[warning] ??
                  "Confira esta sugestão antes de usar."
                }}
              </li>
            </ul>
            <div class="flex flex-wrap gap-2">
              <UiButton
                v-if="!suggestionUsed"
                type="button"
                size="xs"
                data-testid="use-ai-suggestion"
                @click="useSuggestion"
              >
                Usar no rascunho
              </UiButton>
              <UiButton
                v-else
                type="button"
                variant="outline"
                size="xs"
                data-testid="undo-ai-suggestion"
                @click="undoSuggestion"
              >
                Desfazer uso
              </UiButton>
              <UiButton
                type="button"
                variant="outline"
                size="xs"
                @click="discardSuggestion"
              >
                Descartar
              </UiButton>
            </div>
          </section>
        </div>

        <!-- Hashtags: guardadas limpas, lidas com "#" -->
        <div>
          <label
            :for="`tags-${announcement.pk}`"
            class="mb-1 block text-xs font-medium text-muted-foreground"
          >
            Hashtags
          </label>
          <UiInput
            :id="`tags-${announcement.pk}`"
            v-model="hashtagsText"
            name="announcement_hashtags"
            type="text"
            autocomplete="off"
            placeholder="#padaria #fornada"
          />
        </div>

        <!-- Plataformas: pré-marcadas pela regra, o gestor tira ou põe -->
        <fieldset>
          <legend class="mb-1 text-xs font-medium text-muted-foreground">
            Entregar por
          </legend>
          <div class="flex flex-wrap gap-1.5">
            <label
              v-for="option in platformOptions"
              :key="option.value"
              class="inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="
                platforms.includes(option.value)
                  ? 'border-primary bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground hover:bg-muted'
              "
            >
              <!-- Checkbox nativo sr-only preserva a semântica enquanto a pílula amplia o alvo visual. -->
              <input
                type="checkbox"
                class="sr-only"
                :aria-label="option.label"
                :checked="platforms.includes(option.value)"
                @change="togglePlatform(option.value)"
              />
              <Icon :name="platformIcon(option.value)" class="size-3.5" />
              {{ option.label }}
            </label>
          </div>
          <p
            v-if="platforms.length === 0"
            class="mt-1 text-xs text-destructive"
            role="alert"
          >
            Escolha ao menos uma plataforma.
          </p>
        </fieldset>

        <!-- A decisão e a representação enviada não podem morar em telas diferentes.
             A mesma prévia batch/cancelável usada no formulário de campanha acompanha
             toda edição deste rascunho, por plataforma. -->
        <AnnouncementPreview
          :body="body"
          :sku="announcement.sku"
          :platforms="platforms"
          :platform-labels="platformLabels"
          :platform-content="announcement.platform_content"
        />

        <!-- Audiência só governa mensagens diretas. Publicações não têm destinatário individual. -->
        <div v-if="hasDirectMessage" class="rounded-lg bg-muted/50 px-3 py-2">
          <p class="flex items-center gap-1.5 text-sm">
            <Icon name="lucide:users" class="size-4 text-muted-foreground" />
            <span>{{ audience }}</span>
          </p>
          <p v-if="vip" class="mt-0.5 pl-6 text-xs text-muted-foreground">
            {{ vip }}
          </p>
        </div>
        <div v-else class="rounded-lg bg-muted/50 px-3 py-2 text-sm">
          <p class="flex items-center gap-1.5">
            <Icon name="lucide:globe-2" class="size-4 text-muted-foreground" />
            <span>Publicação para o público geral da plataforma</span>
          </p>
          <p class="mt-0.5 pl-6 text-xs text-muted-foreground">
            Não usa lista de contatos nem envia mensagem direta.
          </p>
        </div>
      </div>
    </div>

    <!-- Decisão -->
    <footer
      class="flex flex-wrap items-center gap-2 border-t border-border bg-muted/30 px-4 py-3"
    >
      <div class="w-full">
        <p class="text-sm font-semibold">Como aprovar este anúncio</p>
        <p class="text-xs text-muted-foreground">
          Aprovar confirma esta versão e define quando ela fica pronta para
          entrega. Agende o próximo horário seguro; entregar agora é uma decisão
          separada.
        </p>
      </div>

      <UiButton
        type="button"
        data-testid="schedule-recommended"
        :aria-expanded="scheduling"
        @click="toggleScheduling"
      >
        <Icon name="lucide:clock" class="size-4" />
        {{ scheduling ? "Fechar agendamento" : "Agendar (recomendado)" }}
      </UiButton>

      <UiButton
        type="button"
        data-testid="publish-now"
        :disabled="!canPublishNow"
        variant="outline"
        @click="publishNow"
      >
        <Icon
          :name="busy ? 'line-md:loading-loop' : 'lucide:send'"
          class="size-4"
        />
        {{ deliverNowLabel }}
      </UiButton>

      <UiButton
        type="button"
        :disabled="busy"
        variant="outline"
        class="ml-auto text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
        @click="askToReject"
      >
        <Icon name="lucide:trash-2" class="size-4" />
        Recusar
      </UiButton>

      <p
        v-if="hasDirectMessage && quietHoursSuspendedForLocalSimulation"
        class="w-full text-xs font-medium text-sky-700 dark:text-sky-300"
        role="status"
      >
        Ensaio local: o silêncio 20:00–08:00 está suspenso e nenhuma mensagem
        sai deste computador.
      </p>
      <p
        v-else-if="nowFallsInQuietHours"
        class="w-full text-xs font-medium text-warning"
        role="status"
      >
        WhatsApp em silêncio das 20:00 às 08:00 ({{ timezoneName }}). Agende o
        próximo horário permitido.
      </p>
      <p
        v-else-if="expired"
        class="w-full text-xs font-medium text-destructive"
        role="alert"
      >
        O prazo terminou. Atualize os fatos antes de publicar.
      </p>

      <!-- Agendamento: aparece só quando pedido, para não pesar o caminho comum -->
      <div v-if="scheduling" class="w-full space-y-2 pt-2">
        <div class="flex flex-wrap items-center gap-2">
          <label
            :for="`when-${announcement.pk}`"
            class="text-xs font-medium text-muted-foreground"
            >Entregar em</label
          >
          <UiInput
            :id="`when-${announcement.pk}`"
            v-model="publishAt"
            type="datetime-local"
            :aria-describedby="`when-help-${announcement.pk}`"
            @update:model-value="publishFold = ''"
          />
          <span class="text-xs font-semibold text-muted-foreground">{{
            timezoneName
          }}</span>
          <UiButton type="button" :disabled="!canSchedule" @click="schedule">
            <Icon name="lucide:calendar-check" class="size-4" />
            Confirmar agendamento
          </UiButton>
        </div>
        <p
          v-if="
            scheduleResolution.problem &&
            scheduleResolution.problem !== 'ambiguous'
          "
          :id="`when-help-${announcement.pk}`"
          class="text-xs text-destructive"
          role="alert"
        >
          {{ scheduleResolution.detail }}
          <UiButton
            v-if="scheduleResolution.nextAllowedLocal"
            type="button"
            variant="link"
            class="ml-1"
            @click="useNextAllowedTime"
          >
            Usar 08:00
          </UiButton>
        </p>
        <fieldset
          v-if="scheduleResolution.problem === 'ambiguous'"
          class="rounded-md border border-warning/40 bg-warning/5 p-2"
        >
          <legend class="px-1 text-xs font-semibold">
            Horário repetido pela mudança do relógio
          </legend>
          <p class="text-xs text-muted-foreground">
            {{ scheduleResolution.detail }}
          </p>
          <div class="mt-1 flex flex-wrap gap-3 text-xs">
            <!-- Rádios nativos distinguem as duas ocorrências do mesmo horário ambíguo. -->
            <label
              v-for="(candidate, index) in scheduleResolution.candidates"
              :key="candidate.instant"
              class="flex items-center gap-1.5"
            >
              <input
                v-model="publishFold"
                type="radio"
                :value="index === 0 ? 'earlier' : 'later'"
              />
              {{ index === 0 ? "Primeira" : "Segunda" }} ocorrência (UTC{{
                candidate.offset
              }})
            </label>
          </div>
        </fieldset>
        <p
          v-if="schedulePreview && scheduleResolution.ok"
          class="text-xs text-muted-foreground"
        >
          Será entregue em {{ schedulePreview }} · UTC{{
            scheduleResolution.candidate?.offset
          }}.
          {{
            quietHoursSuspendedForLocalSimulation
              ? "Ensaio local sem efeito externo."
              : "WhatsApp respeita 20:00–08:00."
          }}
        </p>
      </div>
    </footer>
  </article>
</template>
