<script setup lang="ts">
import type { MarketingPlatformCapability } from "~/types/campaign";
import GoogleBusinessPostOptions from "~/components/GoogleBusinessPostOptions.vue";
import {
  googleBusinessEdits,
  googleBusinessOptions,
} from "~/presentation/googleBusinessPost";
import type { GoogleBusinessOptions } from "~/presentation/googleBusinessPost";

const props = defineProps<{
  capability: MarketingPlatformCapability;
  baseBody: string;
  idPrefix: string;
}>();

const composition = defineModel<Record<string, unknown>>({ required: true });

const formatOptions = computed(() =>
  props.capability.formats.map((format) => ({
    value: format.ref,
    label: format.label,
    hint: format.media_required ? "Exige imagem pública." : undefined,
  })),
);
const selectedFormat = computed(() => {
  const requested = String(
    composition.value.publication_format || props.capability.default_format,
  );
  return props.capability.formats.some((format) => format.ref === requested)
    ? requested
    : props.capability.default_format;
});
const bodyOverride = computed(() => String(composition.value.body || ""));
const effectiveBody = computed(() => bodyOverride.value || props.baseBody);
const hasLink = computed(() => effectiveBody.value.includes("{{link}}"));
const selectedFormatLabel = computed(
  () =>
    props.capability.formats.find(
      (format) => format.ref === selectedFormat.value,
    )?.label || selectedFormat.value,
);
const hasExplicitComposition = computed(() =>
  Object.entries(composition.value).some(([key, value]) => {
    if (value === "" || value === null || value === undefined) return false;
    if (key === "publication_format")
      return String(value) !== props.capability.default_format;
    if (key === "call_to_action") return String(value) !== "none";
    return true;
  }),
);
const isGoogle = computed(
  () => props.capability.platform === "google_business",
);
const providerIdPrefix = computed(() =>
  props.capability.platform === "google_business"
    ? props.idPrefix.replace(/google_business$/, "google")
    : props.idPrefix,
);
const googleOptions = computed<GoogleBusinessOptions>({
  get: () => googleBusinessOptions(composition.value),
  set: (options) => {
    const next = { ...composition.value };
    for (const key of [
      "publication_format",
      "call_to_action",
      "event_title",
      "event_start",
      "event_end",
      "offer_terms",
    ]) {
      Reflect.deleteProperty(next, key);
    }
    Object.assign(next, googleBusinessEdits(options));
    composition.value = next;
  },
});

function updateField(key: string, value: unknown) {
  const next = { ...composition.value };
  if (
    value === "" ||
    value === null ||
    value === undefined ||
    (typeof value === "string" && !value.trim())
  )
    Reflect.deleteProperty(next, key);
  else next[key] = value;
  composition.value = next;
}

function updateFormat(value: string) {
  const capability = props.capability.formats.find(
    (format) => format.ref === value,
  );
  if (!capability) return;
  const allowed = new Set(capability.provider_fields);
  const next = { ...composition.value };
  for (const key of Object.keys(next)) {
    if (
      !["body", "hashtags", "image_url", "link"].includes(key) &&
      !allowed.has(key)
    ) {
      Reflect.deleteProperty(next, key);
    }
  }
  if (allowed.has("publication_format")) next.publication_format = value;
  composition.value = next;
}
</script>

<template>
  <details
    class="space-y-4 rounded-lg border border-border bg-card p-4"
    :data-testid="`composition-${capability.platform}`"
  >
    <summary class="cursor-pointer list-none">
      <span class="flex items-center gap-2">
        <strong class="text-sm">{{ capability.label }}</strong>
        <span
          v-if="hasExplicitComposition"
          class="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
        >
          Adaptada
        </span>
        <Icon
          name="lucide:chevron-down"
          class="ml-auto size-4 text-muted-foreground"
        />
      </span>
      <span class="mt-1 block text-xs text-muted-foreground">
        {{
          capability.delivery_kind === "direct_message"
            ? "Mensagem direta"
            : "Publicação pública"
        }}
        · {{ selectedFormatLabel }}
      </span>
    </summary>

    <div class="mt-4 space-y-4 border-t border-border pt-4">
      <GoogleBusinessPostOptions
        v-if="isGoogle"
        v-model="googleOptions"
        :id-prefix="providerIdPrefix"
        :has-link="hasLink"
      />

      <div v-else-if="capability.formats.length > 1">
        <p class="mb-1 text-xs font-medium text-muted-foreground">Formato</p>
        <UiRadioGroup
          :model-value="selectedFormat"
          :label="`Formato em ${capability.label}`"
          :options="formatOptions"
          class="sm:grid-flow-col sm:auto-cols-fr"
          @update:model-value="updateFormat(String($event))"
        />
      </div>

      <div>
        <label
          :for="`${idPrefix}-body`"
          class="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Texto só para {{ capability.label }} (opcional)
        </label>
        <UiTextarea
          :id="`${idPrefix}-body`"
          :model-value="bodyOverride"
          :rows="3"
          class="resize-y"
          :placeholder="baseBody || 'Usa o texto comum quando ficar vazio.'"
          @update:model-value="updateField('body', String($event ?? ''))"
        />
        <p class="mt-1 text-xs text-muted-foreground">
          Vazio usa o texto comum. A adaptação fica explícita e salva somente
          para este destino.
        </p>
      </div>

      <p
        v-if="capability.delivery_kind === 'direct_message'"
        class="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground"
      >
        Modelo, variáveis e botões aprovados são definidos na conexão da
        plataforma; esta composição não inventa opções fora desse contrato.
      </p>
    </div>
  </details>
</template>
