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
  isQuietHoursNow,
  resolveScheduleInput,
  scheduleSummary,
  suggestedScheduleLocal,
} from "~/utils/marketingSchedule";
import type { ScheduleFold } from "~/utils/marketingSchedule";
import {
  audienceSummary,
  displayHashtag,
  parseHashtags,
  platformIcon,
  platformsSummary,
  vipSummary,
} from "~/presentation/campaign";
import {
  includesDirectMessage,
  outgoingImageUrl,
} from "~/presentation/marketingDelivery";
import {
  platformReadinessNote,
  readinessByPlatform,
} from "~/presentation/platformReadiness";
import type { PlatformReadiness } from "~/presentation/platformReadiness";
import {
  googleBusinessEdits,
  googleBusinessOptions,
  googleCallToActionLabel,
  googlePostTypeLabel,
} from "~/presentation/googleBusinessPost";
import type { GoogleBusinessOptions } from "~/presentation/googleBusinessPost";

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
  /** Estado e motivo por plataforma (`/marketing/platforms/`). Ausente = tudo pronto. */
  platformReadiness?: PlatformReadiness[];
  /** Produtos publicáveis (`options.products`): o nome que o gestor fala, no lugar
   *  do SKU. Sem rótulo, o SKU continua sendo o que há. */
  productOptions?: { value: string; label: string }[];
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
// O post do Google (tipo e botão) parte do que o modelo gravou e é decidido aqui.
const googleOptions = ref<GoogleBusinessOptions>(
  googleBusinessOptions(props.announcement.platform_content?.google_business),
);
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
    googleOptions.value = googleBusinessOptions(
      props.announcement.platform_content?.google_business,
    );
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
    google_business: googleBusinessOptions(
      props.announcement.platform_content?.google_business,
    ),
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
    google_business: { ...googleOptions.value },
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
  googleOptions.value = googleBusinessOptions(
    payload.google_business && typeof payload.google_business === "object"
      ? (payload.google_business as Record<string, unknown>)
      : props.announcement.platform_content?.google_business,
  );
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
  google_business: "Post no Google",
  scheduling: "Agendamento",
  publish_at: "Data e hora",
  publish_fold: "Ocorrência do horário",
};

/** Nome do produto quando o catálogo o deu; o SKU só como último recurso. */
/** A foto que realmente vai com o anúncio. Ver o aviso no template: o campo do topo
 *  quase sempre está vazio, e a imagem mora no conteúdo por plataforma. */
const outgoingImage = computed(() => outgoingImageUrl(props.announcement));

const productLabel = computed(() => {
  const sku = props.announcement.sku;
  if (!sku) return "";
  return (
    props.productOptions?.find((option) => option.value === sku)?.label || sku
  );
});

// Prontidão por plataforma, antes do clique: pílula pintada e frase sob a escolha.
const readinessMap = computed(() =>
  readinessByPlatform(props.platformReadiness),
);
function readinessNote(option: { value: string; label: string }) {
  return platformReadinessNote(readinessMap.value[option.value], option.label);
}
const selectedReadinessNotes = computed(() =>
  props.platformOptions
    .filter((option) => platforms.value.includes(option.value))
    .map((option) => ({ platform: option.value, ...readinessNote(option) }))
    .filter((note) => note.tone !== "ready"),
);

/** O aviso de conflito mostra nomes de plataforma, não a lista de refs em JSON. */
function describeDraftValue(field: string, value: unknown): string | undefined {
  if (field === "platforms" && Array.isArray(value)) {
    return platformsSummary(value.map(String), platformLabels.value);
  }
  // ⚠️ Booleano cru no aviso de conflito lia "Agendamento — Versão atual: não · Seu
  // rascunho: sim", que não quer dizer nada. A porta para traduzir já existia; só
  // estava servindo a plataforma e mais ninguém.
  if (field === "scheduling") return value ? "agendado" : "disparar agora";
  if (field === "google_business" && value && typeof value === "object") {
    const options = googleBusinessOptions(value as Record<string, unknown>);
    const button = googleCallToActionLabel(options.call_to_action);
    return `${googlePostTypeLabel(options.publication_format)}${
      options.publication_format === "offer"
        ? ""
        : ` · botão ${button ? `“${button}”` : "nenhum"}`
    }`;
  }
  return undefined;
}

const timezoneName = computed(() => props.shopTimezone || "UTC");
const expiresAtMs = computed(() => Date.parse(props.announcement.expires_at));
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
const hasDirectMessage = computed(() => includesDirectMessage(platforms.value));
const nowFallsInQuietHours = computed(
  () =>
    hasDirectMessage.value &&
    !props.quietHoursSuspendedForLocalSimulation &&
    isQuietHoursNow(timezoneName.value, clockMs.value),
);
const canPublishNow = computed(
  () => canPublish.value && !nowFallsInQuietHours.value,
);
/** Agendar só é "recomendado" com motivo: o agora cai no silêncio do WhatsApp. */
const scheduleRecommended = computed(() => nowFallsInQuietHours.value);
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

const publishesOnGoogle = computed(() =>
  platforms.value.includes("google_business"),
);
/** A prévia confere o post do Google com as escolhas feitas aqui, antes de aprovar. */
const previewGoogleBusiness = computed(() =>
  publishesOnGoogle.value
    ? googleBusinessEdits(googleOptions.value)
    : undefined,
);

function edits(): AnnouncementEdits {
  return {
    body: body.value.trim(),
    hashtags: parseHashtags(hashtagsText.value),
    platforms: [...platforms.value],
    ...(publishesOnGoogle.value
      ? { google_business: googleBusinessEdits(googleOptions.value) }
      : {}),
    ...(acceptedSuggestionRef.value
      ? { ai_suggestion_ref: acceptedSuggestionRef.value }
      : {}),
  };
}

function publishNow() {
  if (!canPublishNow.value) return;
  draft.flush();
  emit("approve", props.announcement.pk, editsWithPhoto(), "now");
}

function schedule() {
  if (!canSchedule.value || !scheduleResolution.value.candidate) return;
  draft.flush();
  emit(
    "approve",
    props.announcement.pk,
    { ...editsWithPhoto(), publish_at: scheduleResolution.value.candidate.instant },
    "scheduled",
  );
}

/** Ligar "Agendado" já traz um horário sugerido — quem escolheu agendar não deve
 *  encontrar um campo vazio e ter que inventar a hora do zero. */
function openScheduling() {
  scheduling.value = true;
  if (publishAt.value) return;
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

// ── Revisão v4 (MKT-14) ─────────────────────────────────────────────────────

/** "Rascunho do lote: Croissant, 24 un" (v3 a): de onde o rascunho veio. */
const draftOrigin = computed(() => {
  const product = productLabel.value;
  const quantity = props.announcement.lot_quantity
    ? `, ${props.announcement.lot_quantity.replace(".", ",")} un`
    : "";
  if (props.announcement.lot_quantity && product) return `Rascunho do lote: ${product}${quantity}`;
  if (props.announcement.template_name) return `Rascunho do modelo: ${props.announcement.template_name}`;
  return "";
});

function clockOf(instant: string): string {
  const ms = Date.parse(instant);
  if (!Number.isFinite(ms)) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezoneName.value,
  }).format(new Date(ms));
}

// "Tirar outra" (MKT-17): a câmera do dispositivo, sem sair do fluxo. A foto vai ao
// servidor (que a regrava em JPEG, sem os metadados da câmera) e o endereço viaja
// junto com a aprovação, como o texto: o selo congela o que a pessoa conferiu.
const photoUrl = ref("");
const photoBusy = ref(false);
const photoError = ref("");
const photoInput = ref<HTMLInputElement | null>(null);
const shownPhoto = computed(() => photoUrl.value || outgoingImage.value);
const photoCaption = computed(() => {
  if (photoUrl.value) return "Foto tirada agora";
  const at = props.announcement.lot_finished_at ? clockOf(props.announcement.lot_finished_at) : "";
  return props.announcement.lot_quantity ? `Foto do lote${at ? `, ${at}` : ""}` : "Foto do produto";
});

async function onPhotoPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  photoBusy.value = true;
  photoError.value = "";
  try {
    const form = new FormData();
    form.append("photo", file);
    const response = await $fetch<{ image_url: string }>(
      `/api/v1/backstage/marketing/announcements/${props.announcement.pk}/photo/`,
      { method: "POST", credentials: "same-origin", body: form },
    );
    photoUrl.value = response.image_url;
  } catch (err) {
    flagMarketingSessionError(err);
    photoError.value = httpErrorMessage(err, "A foto não subiu. A anterior continua.");
  } finally {
    photoBusy.value = false;
  }
}

// O limite do texto é o da plataforma mais curta escolhida (v3 a: "118 / 2.200").
const TEXT_LIMITS: Record<string, number> = {
  instagram: 2200,
  facebook: 63206,
  google_business: 1500,
  whatsapp: 1024,
};
const textLimit = computed(() => {
  const limits = platforms.value.map((ref) => TEXT_LIMITS[ref]).filter((value): value is number => Boolean(value));
  return limits.length ? Math.min(...limits) : 2200;
});
const textLength = computed(() => body.value.length);
const formatCountPt = (value: number) => new Intl.NumberFormat("pt-BR").format(value);

/** As linhas de plataforma (v3 a): nome, o que é ali, e a chave. */
const PLATFORM_ROW_LABELS: Record<string, { label: string; kind: string }> = {
  instagram: { label: "Instagram", kind: "feed e story" },
  facebook: { label: "Facebook", kind: "" },
  google_business: { label: "Google", kind: "perfil da loja" },
  whatsapp: { label: "WhatsApp", kind: "mensagem direta" },
};
function rowLabel(option: { value: string; label: string }) {
  return PLATFORM_ROW_LABELS[option.value]?.label ?? option.label;
}
function rowKind(option: { value: string; label: string }): string {
  const kind = PLATFORM_ROW_LABELS[option.value]?.kind ?? "";
  if (option.value !== "whatsapp") return kind;
  const total = props.announcement.audience_total;
  return total ? `${kind} · ${formatCountPt(total)} ${total === 1 ? "cliente" : "clientes"}` : kind;
}

/** Uma frase para o que está fora (MKT-16), em vez de um parágrafo por plataforma. */
const readinessSummary = computed(() => {
  const notes = selectedReadinessNotes.value;
  if (!notes.length) return null;
  const names = notes.map((note) => PLATFORM_ROW_LABELS[note.platform]?.label ?? note.platform);
  const joined = names.length > 1 ? `${names.slice(0, -1).join(", ")} e ${names.at(-1)}` : names[0];
  const blocked = notes.some((note) => note.tone === "blocked");
  const switchedOff = notes.every((note) => note.badge === "desligada");
  if (switchedOff) {
    return {
      tone: "blocked" as const,
      text: `${joined} ${names.length > 1 ? "estão desligados" : "está desligado"} neste ambiente: o que for aprovado fica na fila até ligar.`,
      link: true,
    };
  }
  return {
    tone: blocked ? ("blocked" as const) : ("limited" as const),
    text: notes.map((note) => note.text).join(" "),
    link: notes.some((note) => note.tone !== "limited"),
  };
});

const showPreview = ref(false);
const showHashtags = ref(props.announcement.hashtags.length > 0);

function editsWithPhoto(): AnnouncementEdits {
  return photoUrl.value ? { ...edits(), image_url: photoUrl.value } : edits();
}

defineExpose({ openScheduling, askToReject });
</script>

<template>
  <!-- A revisão do anúncio (v4 "a revisão aberta" e v3 a "revisar o anúncio do lote"):
       a origem escrita, a foto grande com "Tirar outra", o texto com o limite da
       plataforma, as plataformas numa lista com chave por linha, e "Recusar" +
       "Continuar" fixos no polegar. O prazo mora no cabeçalho da tela. -->
  <article class="flex flex-col gap-4 pb-28 sm:pb-0" data-announcement-review>
    <p class="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px]" data-review-origin>
      <span class="inline-flex h-7 items-center gap-1.5 rounded-full bg-warning/12 px-2.5 font-semibold text-warning">
        <span class="size-1.5 rounded-full bg-warning" aria-hidden="true" />Pede sua aprovação
      </span>
      <span v-if="draftOrigin" class="text-muted-foreground">{{ draftOrigin }}</span>
      <span
        v-else-if="announcement.sku"
        class="text-muted-foreground"
        :class="productLabel === announcement.sku ? 'font-mono' : ''"
      >{{ productLabel }}</span>
    </p>

    <DraftRecoveryNotice
      :state="draft.state.value"
      :saved-at="draft.savedAt.value"
      :conflicts="draft.conflicts.value"
      :labels="DRAFT_LABELS"
      :describe="describeDraftValue"
      @keep-local="draft.keepLocal()"
      @keep-server="draft.keepServer()"
      @discard="draft.discard()"
    />

    <!-- A foto como vai sair, grande. ⚠️ A imagem de verdade costuma morar no conteúdo
         POR PLATAFORMA: `outgoingImageUrl()` lê os dois, como a caixa de confirmação. -->
    <figure class="relative overflow-hidden rounded-2xl border border-border bg-muted/40" data-review-photo>
      <img
        v-if="shownPhoto"
        :src="shownPhoto"
        :alt="`Foto de ${productLabel || 'produto'}`"
        class="h-56 w-full object-cover sm:h-72"
      >
      <div v-else class="grid h-56 w-full place-content-center justify-items-center gap-1.5 text-sm text-muted-foreground sm:h-72">
        <Icon name="lucide:image-off" class="size-7" aria-hidden="true" />
        Sem foto
      </div>
      <span
        v-if="shownPhoto"
        class="absolute top-3 left-3 inline-flex h-8 items-center gap-1.5 rounded-full bg-black/55 px-3 text-[13px] font-semibold text-white backdrop-blur-sm"
      >
        <Icon name="lucide:image" class="size-4" aria-hidden="true" />{{ photoCaption }}
      </span>
      <button
        type="button"
        class="absolute right-3 bottom-3 inline-flex h-11 items-center gap-2 rounded-full bg-card/95 px-4 text-[14px] font-semibold text-foreground shadow-sm disabled:opacity-60"
        :disabled="photoBusy || busy"
        data-review-retake
        @click="photoInput?.click()"
      >
        <Icon :name="photoBusy ? 'lucide:loader-circle' : 'lucide:camera'" class="size-5" :class="photoBusy ? 'animate-spin' : ''" aria-hidden="true" />
        {{ photoBusy ? "Enviando a foto…" : shownPhoto ? "Tirar outra" : "Tirar foto" }}
      </button>
      <input
        ref="photoInput"
        type="file"
        accept="image/*"
        capture="environment"
        class="sr-only"
        aria-label="Tirar a foto do lote"
        tabindex="-1"
        @change="onPhotoPicked"
      >
    </figure>
    <p v-if="photoError" class="-mt-2 text-[13px] text-destructive" role="alert">{{ photoError }}</p>

    <!-- O texto: editável no lugar, com o limite da plataforma mais curta escolhida. -->
    <div>
      <div class="mb-1.5 flex items-center justify-between gap-2">
        <label :for="`body-${announcement.pk}`" class="op-eyebrow text-muted-foreground">Texto</label>
        <span class="flex items-center gap-2">
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
          <span
            class="op-micro tnum"
            :class="textLength > textLimit ? 'font-semibold text-destructive' : 'text-muted-foreground'"
            data-review-counter
          >{{ formatCountPt(textLength) }} / {{ formatCountPt(textLimit) }}</span>
        </span>
      </div>
      <UiTextarea
        :id="`body-${announcement.pk}`"
        v-model="body"
        name="announcement_body"
        :rows="4"
        autocomplete="off"
        class="resize-y rounded-xl text-[16px] leading-relaxed"
      />
      <p v-if="!body.trim()" class="mt-1 text-xs text-destructive" role="alert">O anúncio precisa de um texto.</p>
      <p v-else-if="textLength > textLimit" class="mt-1 text-xs text-destructive" role="alert">
        O texto passou do limite da plataforma mais curta escolhida.
      </p>
      <p
        v-if="assistError"
        class="mt-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        role="alert"
        data-testid="ai-assist-error"
      >{{ assistError }}</p>
      <section
        v-if="suggestion"
        class="mt-3 space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
        aria-label="Comparação da sugestão de IA"
        data-testid="ai-suggestion-compare"
      >
        <div>
          <p class="text-sm font-semibold">Sugestão pronta para comparar</p>
          <p class="text-xs text-muted-foreground">Usar muda só este rascunho. Nada é publicado.</p>
        </div>
        <div class="grid gap-2 sm:grid-cols-2">
          <div class="rounded-md border border-border bg-background p-2">
            <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Seu texto</p>
            <p class="whitespace-pre-wrap text-sm">{{ beforeSuggestion?.body }}</p>
          </div>
          <div class="rounded-md border border-primary/30 bg-background p-2">
            <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-primary">Sugestão</p>
            <p class="whitespace-pre-wrap text-sm">{{ suggestion.body }}</p>
            <p v-if="suggestion.hashtags.length" class="mt-2 text-xs text-muted-foreground">
              {{ suggestion.hashtags.map(displayHashtag).join(" ") }}
            </p>
          </div>
        </div>
        <div v-if="suggestion.facts.length" class="text-xs">
          <p class="font-semibold">Dados usados</p>
          <ul class="mt-1 flex flex-wrap gap-1.5">
            <li v-for="fact in suggestion.facts" :key="fact.id" class="rounded-full border border-border bg-background px-2 py-1">
              {{ fact.label }}: {{ fact.value }}
            </li>
          </ul>
        </div>
        <ul v-if="suggestion.warnings.length" class="space-y-1 text-xs text-warning">
          <li v-for="warning in suggestion.warnings" :key="warning">
            {{ warningLabels[warning] ?? "Confira esta sugestão antes de usar." }}
          </li>
        </ul>
        <div class="flex flex-wrap gap-2">
          <UiButton v-if="!suggestionUsed" type="button" size="xs" data-testid="use-ai-suggestion" @click="useSuggestion">
            Usar no rascunho
          </UiButton>
          <UiButton v-else type="button" variant="outline" size="xs" data-testid="undo-ai-suggestion" @click="undoSuggestion">
            Desfazer uso
          </UiButton>
          <UiButton type="button" variant="outline" size="xs" @click="discardSuggestion">Descartar</UiButton>
        </div>
      </section>

      <!-- Hashtags: guardadas limpas, lidas com "#". Uma linha discreta sob o texto. -->
      <div class="mt-2">
        <button
          v-if="!showHashtags"
          type="button"
          class="inline-flex min-h-9 items-center gap-1 text-[13px] font-medium text-muted-foreground underline underline-offset-2"
          @click="showHashtags = true"
        >
          <Icon name="lucide:hash" class="size-3.5" aria-hidden="true" />Pôr hashtags
        </button>
        <template v-else>
          <label :for="`tags-${announcement.pk}`" class="sr-only">Hashtags</label>
          <UiInput
            :id="`tags-${announcement.pk}`"
            v-model="hashtagsText"
            name="announcement_hashtags"
            type="text"
            autocomplete="off"
            placeholder="Hashtags, ex.: #padaria #croissant"
            class="h-10 text-[14px]"
          />
        </template>
      </div>
    </div>

    <!-- Plataformas: uma linha por plataforma, com a chave (v3 a). Publicação pública e
         mensagem direta separadas pela segunda linha de cada uma. -->
    <fieldset>
      <legend class="sr-only">Disparado via</legend>
      <ul class="rounded-2xl border border-border bg-card px-4" data-review-platforms>
        <li
          v-for="option in platformOptions"
          :key="option.value"
          class="flex min-h-[60px] items-center gap-3 py-2 [&+&]:border-t [&+&]:border-border"
          :data-readiness="readinessNote(option).tone"
          :data-review-platform="option.value"
        >
          <Icon :name="platformIcon(option.value)" class="size-5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 flex-1 leading-tight">
            <span class="text-[16px]">{{ rowLabel(option) }}</span>
            <span v-if="rowKind(option)" class="ml-1.5 text-[13px] text-muted-foreground">{{ rowKind(option) }}</span>
            <span
              v-if="readinessNote(option).badge"
              class="block text-[12px] font-medium"
              :class="readinessNote(option).tone === 'blocked' ? 'text-destructive' : 'text-warning'"
            >{{ readinessNote(option).badge }}</span>
          </span>
          <UiSwitch
            :model-value="platforms.includes(option.value)"
            :aria-label="`${platforms.includes(option.value) ? 'Tirar' : 'Pôr'} ${rowLabel(option)}`"
            @update:model-value="togglePlatform(option.value)"
          />
        </li>
      </ul>
      <p v-if="platforms.length === 0" class="mt-1 text-xs text-destructive" role="alert">Escolha ao menos uma plataforma.</p>
      <!-- Aprovar continua possível (a pré-condição é de publicar): o gestor só fica
           sabendo AGORA, e não no comprovante, onde o anúncio não vai sair. Uma frase
           só para todas, não um parágrafo por plataforma. -->
      <p
        v-if="readinessSummary"
        class="mt-2 text-[13px]"
        :class="readinessSummary.tone === 'blocked' ? 'text-destructive' : 'text-warning'"
        role="status"
        data-review-readiness
      >
        {{ readinessSummary.text }}
        <NuxtLink v-if="readinessSummary.link" to="/settings/platforms" class="font-semibold underline">Ver em Ajustes › Plataformas</NuxtLink>
      </p>
      <p v-if="hasDirectMessage" class="mt-2 text-[13px] text-muted-foreground" data-review-audience>
        <Icon name="lucide:users" class="mr-1 inline size-4 align-[-3px]" aria-hidden="true" />{{ audience }}<template v-if="vip"> · {{ vip }}</template>
      </p>
      <p v-else class="mt-2 text-[13px] text-muted-foreground">
        <Icon name="lucide:globe-2" class="mr-1 inline size-4 align-[-3px]" aria-hidden="true" />Postagem pública. Não escolhe contatos.
      </p>
    </fieldset>

    <GoogleBusinessPostOptions
      v-if="publishesOnGoogle"
      v-model="googleOptions"
      :id-prefix="`google-${announcement.pk}`"
      :has-link="!!announcement.link"
    />

    <!-- Como fica em cada plataforma: a mesma prévia do formulário de campanha, lida do
         conteúdo GRAVADO do anúncio com as edições daqui. Abre sob pedido: a revisão já
         mostra a foto e o texto. -->
    <div>
      <button
        type="button"
        class="inline-flex min-h-11 items-center gap-1.5 text-[14px] font-semibold text-foreground"
        :aria-expanded="showPreview"
        data-review-preview-toggle
        @click="showPreview = !showPreview"
      >
        <Icon :name="showPreview ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" aria-hidden="true" />
        Ver como fica em cada plataforma
      </button>
      <AnnouncementPreview
        v-if="showPreview"
        class="mt-2"
        :body="body"
        :announcement-id="announcement.pk"
        :hashtags="parseHashtags(hashtagsText)"
        :platforms="platforms"
        :platform-labels="platformLabels"
        :google-business="previewGoogleBusiness"
      />
    </div>

    <!-- Quando: atributo do disparo, não destino. Agora é o padrão; agendar abre a hora. -->
    <div class="rounded-2xl border border-border bg-card px-4 py-3" data-review-when>
      <div class="flex items-center gap-3">
        <span class="flex-1 text-[15px]">Quando</span>
        <div role="group" aria-label="Disparo" class="flex gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            data-testid="delivery-now"
            :aria-pressed="!scheduling"
            class="min-h-10 rounded-md px-4 text-sm transition"
            :class="scheduling ? 'font-medium text-muted-foreground' : 'bg-card font-semibold shadow-sm'"
            @click="scheduling = false"
          >
            Imediato
          </button>
          <button
            type="button"
            data-testid="delivery-scheduled"
            :aria-pressed="scheduling"
            class="min-h-10 rounded-md px-4 text-sm transition"
            :class="scheduling ? 'bg-card font-semibold shadow-sm' : 'font-medium text-muted-foreground'"
            @click="openScheduling"
          >
            Agendado
          </button>
        </div>
      </div>
      <p
        v-if="hasDirectMessage && quietHoursSuspendedForLocalSimulation"
        class="mt-2 text-xs font-medium text-sky-700 dark:text-sky-300"
        role="status"
      >
        Ensaio local: o silêncio das 20:00 às 08:00 está suspenso e nenhuma mensagem é enviada deste computador.
      </p>
      <p v-else-if="scheduleRecommended" class="mt-2 text-xs font-medium text-warning" role="status">
        O WhatsApp está em silêncio das 20:00 às 08:00 ({{ timezoneName }}). Envio imediato fica indisponível até as
        08:00. Em Agendado, o próximo horário permitido já vem preenchido.
      </p>

      <div v-if="scheduling" class="mt-3 space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <label :for="`when-${announcement.pk}`" class="text-xs font-medium text-muted-foreground">Disparar em</label>
          <UiDateTimeField
            :id="`when-${announcement.pk}`"
            v-model="publishAt"
            label="Data e hora do disparo"
            :aria-describedby="`when-help-${announcement.pk}`"
            @update:model-value="publishFold = ''"
          />
          <span class="text-xs font-semibold text-muted-foreground">{{ timezoneName }}</span>
        </div>
        <p
          v-if="scheduleResolution.problem && scheduleResolution.problem !== 'ambiguous'"
          :id="`when-help-${announcement.pk}`"
          class="text-xs text-destructive"
          role="alert"
        >
          {{ scheduleResolution.detail }}
          <UiButton v-if="scheduleResolution.nextAllowedLocal" type="button" variant="link" class="ml-1" @click="useNextAllowedTime">
            Usar o próximo horário permitido
          </UiButton>
        </p>
        <fieldset v-if="scheduleResolution.problem === 'ambiguous'" class="rounded-md border border-warning/40 bg-warning/5 p-2">
          <legend class="px-1 text-xs font-semibold">Horário repetido pela mudança do relógio</legend>
          <p class="text-xs text-muted-foreground">{{ scheduleResolution.detail }}</p>
          <UiRadioGroup v-model="publishFold" label="Qual das duas ocorrências" orientation="horizontal" class="mt-1 text-xs">
            <UiRadio
              v-for="(candidate, index) in scheduleResolution.candidates"
              :key="candidate.instant"
              :value="index === 0 ? 'earlier' : 'later'"
              variant="inline"
              :label="`${index === 0 ? 'Primeira' : 'Segunda'} ocorrência (UTC${candidate.offset})`"
            />
          </UiRadioGroup>
        </fieldset>
        <p v-if="schedulePreview && scheduleResolution.ok" class="text-xs text-muted-foreground">
          Será entregue em {{ schedulePreview }} · UTC{{ scheduleResolution.candidate?.offset }}.
          {{ quietHoursSuspendedForLocalSimulation ? "Ensaio local sem efeito externo." : "WhatsApp respeita o silêncio das 20:00 às 08:00." }}
        </p>
      </div>
    </div>

    <p v-if="expired" class="text-xs font-medium text-destructive" role="alert">
      O prazo deste anúncio venceu: preço e estoque já podem ter mudado.
      <NuxtLink to="/settings/campaigns" class="font-semibold underline">Prepare um disparo novo em Campanhas.</NuxtLink>
    </p>

    <!-- A decisão, fixa no polegar (v3 a). ⚠️ "Continuar" é pedido do dono: este botão
         não dispara, leva ao selo, e lá o ato tem o nome (Publicar e enviar, Agendar).
         Recusar ANTES, da mesma largura. -->
    <footer
      class="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-card/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:static sm:rounded-2xl sm:border sm:bg-card sm:pb-3"
      data-review-actions
    >
      <div class="mx-auto flex max-w-2xl gap-2.5">
        <UiButton
          type="button"
          :disabled="busy"
          variant="outline"
          class="h-14 flex-1 basis-0 rounded-xl text-[16px] font-semibold sm:h-12 sm:flex-none sm:basis-auto sm:px-6"
          @click="askToReject"
        >
          Recusar
        </UiButton>
        <UiButton
          type="button"
          data-testid="publish-now"
          :disabled="(scheduling ? !canSchedule : !canPublishNow) || textLength > textLimit"
          class="h-14 flex-[2] basis-0 rounded-xl text-[16px] font-semibold sm:h-12 sm:flex-1"
          @click="scheduling ? schedule() : publishNow()"
        >
          <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:arrow-right'" class="size-5" aria-hidden="true" />
          Continuar
        </UiButton>
      </div>
      <p class="mt-1.5 text-center text-[12px] text-muted-foreground">
        O texto que você conferir na próxima tela é o que vai: agora, ou na hora que você marcar.
      </p>
    </footer>
  </article>
</template>
