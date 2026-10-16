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
const open = ref(false);
const deliveryLabel = computed(() =>
  props.capability.delivery_kind === "direct_message"
    ? "Mensagem direta"
    : "Publicação pública",
);

const formatOptions = computed(() =>
  props.capability.formats.map((format) => ({
    value: format.ref,
    label: format.label,
    description: format.media_required ? "Exige imagem pública." : undefined,
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
  <!-- Cada destino é uma exceção que se abre só quando precisa: fechado, diz o formato;
       aberto, mostra o formato e o texto próprio. O conteúdo fica montado fechado
       (`unmount-on-hide` falso), para o rascunho e os campos não sumirem do DOM. -->
  <NuxtCard :data-testid="`composition-${capability.platform}`">
    <NuxtCollapsible v-model:open="open" :unmount-on-hide="false">
      <NuxtButton
        color="neutral"
        variant="ghost"
        block
        :trailing-icon="open ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
        class="justify-start text-left"
        data-composition-toggle
      >
        <span class="min-w-0 flex-1">
          <span class="flex flex-wrap items-center gap-2">
            <span class="text-sm font-semibold">{{ capability.label }}</span>
            <NuxtBadge
              v-if="hasExplicitComposition"
              color="primary"
              label="Adaptada"
            />
          </span>
          <span class="mt-0.5 block text-xs font-normal text-muted-foreground">
            {{ deliveryLabel }} · {{ selectedFormatLabel }}
          </span>
        </span>
      </NuxtButton>

      <template #content>
        <div class="mt-3 space-y-4 border-t border-default pt-4">
          <GoogleBusinessPostOptions
            v-if="isGoogle"
            v-model="googleOptions"
            :id-prefix="providerIdPrefix"
            :has-link="hasLink"
          />

          <NuxtRadioGroup
            v-else-if="capability.formats.length > 1"
            :model-value="selectedFormat"
            legend="Formato"
            :aria-label="`Formato em ${capability.label}`"
            :items="formatOptions"
            @update:model-value="updateFormat(String($event))"
          />

          <NuxtFormField
            :label="`Texto só para ${capability.label} (opcional)`"
            help="Vazio usa o texto comum. A adaptação fica explícita e salva somente para este destino."
          >
            <NuxtTextarea
              :id="`${idPrefix}-body`"
              :model-value="bodyOverride"
              :rows="3"
              autoresize
              class="w-full"
              :placeholder="baseBody || 'Usa o texto comum quando ficar vazio.'"
              @update:model-value="updateField('body', String($event ?? ''))"
            />
          </NuxtFormField>

          <p
            v-if="capability.delivery_kind === 'direct_message'"
            class="text-xs text-muted-foreground"
          >
            Modelo, variáveis e botões aprovados são definidos na conexão da
            plataforma; esta composição não inventa opções fora desse contrato.
          </p>
        </div>
      </template>
    </NuxtCollapsible>
  </NuxtCard>
</template>
