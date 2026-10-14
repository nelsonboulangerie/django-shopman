<script setup lang="ts">
// Criar produto do zero e duplicar (7.2, onda 1). Presentacional: o pai é dono do
// fetch/save (useCatalogMatrix). O rascunho do GTIN chega pronto, com a ORIGEM por
// campo; aqui o operador revisa, marca o que confere e o servidor aplica pelo
// mesmo aceite campo a campo do Admin (nada é gravado pela consulta).
import type {
  CorrelateResult,
  CreateProductPayload,
  ProductDraft,
} from "~/types/catalog";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import { useDirtyForm } from "../../../operator-kit/app/composables/useDirtyForm";

const props = defineProps<{
  open: boolean;
  mode: "create" | "duplicate";
  source?: { sku: string; name: string } | null;
  suggestedSku?: string;
  suggestedName?: string;
  busy?: boolean;
  error?: string;
  draft: ProductDraft | null;
  draftBusy: boolean;
  draftError: string;
  enhance: (image: string) => Promise<string>;
  upload: (image: string) => Promise<string>;
  adminBaseUrl?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: CreateProductPayload];
  lookup: [gtin: string];
  "go-purchase": [];
}>();

// A INTENÇÃO vem antes do formulário: é ela que diz o que o cadastro é, e cada
// resposta conduz por um caminho diferente (offerman só tem vendável).
const intent = ref<"revenda" | "producao" | "insumo" | "">("");
const linkPurchase = ref(false);
const intents = [
  {
    value: "revenda" as const,
    label: "Compro e revendo",
    help: "Cria o vendável e oferece ligar o comprável do mesmo SKU.",
  },
  {
    value: "producao" as const,
    label: "Produzo e vendo aqui",
    help: "Cria o vendável e aponta a ficha de execução na Produção.",
  },
  {
    value: "insumo" as const,
    label: "Só compro (insumo)",
    help: "Insumo não entra no catálogo: o cadastro é no Compras.",
  },
];

const form = reactive({
  sku: "",
  name: "",
  priceText: "",
  unit: "un",
  short_description: "",
  long_description: "",
  keywordsText: "",
  image_url: "",
  availability_policy: "planned_ok",
  shelf_life_days: "",
  storage_tip: "",
  ingredients_text: "",
  unit_weight_g: "",
  is_batch_produced: false,
  is_published: true,
  is_sellable: true,
  fiscal_profile: "",
});

const gtin = ref("");
const accepted = ref<Set<string>>(new Set());
const photoBusy = ref(false);
const photoError = ref("");
const photoOriginal = ref("");
const photoResult = ref("");
const uploadBusy = ref(false);
const uploadedUrl = ref("");

const isDuplicate = computed(() => props.mode === "duplicate");
const title = computed(() =>
  isDuplicate.value ? "Duplicar produto" : "Novo produto",
);
const subtitle = computed(() =>
  isDuplicate.value
    ? props.source
      ? "Cópia de " + props.source.name + " (" + props.source.sku + ")"
      : ""
    : "Cria um produto do zero. Publicar em canal e colecionar são gestos da matriz.",
);
const duplicateNote = computed(
  () =>
    "A cópia traz o conteúdo do original (campos, palavras-chave, rótulos e a composição do combo). " +
    "Não traz preço por canal, publicação nem coleção: a cópia nasce oculta e fora de venda, e o GTIN fica de fora. " +
    "Confira e publique na matriz.",
);

const policyOptions = [
  { value: "stock_only", label: "Somente estoque" },
  { value: "planned_ok", label: "Aceita planejado" },
  { value: "demand_ok", label: "Aceita demanda" },
];

const scanner = useBarcodeScanner((code) => {
  gtin.value = code.trim();
  lookup();
});

function resetForm() {
  intent.value = "";
  linkPurchase.value = false;
  gtin.value = "";
  accepted.value = new Set();
  photoResult.value = "";
  photoError.value = "";
  form.sku = isDuplicate.value ? (props.suggestedSku ?? "") : "";
  form.name = isDuplicate.value
    ? (props.suggestedName ?? props.source?.name ?? "")
    : "";
  form.priceText = "";
  form.unit = "un";
  form.short_description = "";
  form.long_description = "";
  form.keywordsText = "";
  form.image_url = "";
  form.availability_policy = "planned_ok";
  form.shelf_life_days = "";
  form.storage_tip = "";
  form.ingredients_text = "";
  form.unit_weight_g = "";
  form.is_batch_produced = false;
  form.is_published = true;
  form.is_sellable = true;
  form.fiscal_profile = "";
}

// O casco de cadastro cuida do aviso, do descarte e do próximo foco; aqui mora
// só o retrato do que o operador mexeu.
const { dirty, changedKeys, capture } = useDirtyForm(() => ({
  intent: intent.value,
  linkPurchase: linkPurchase.value,
  gtin: gtin.value,
  accepted: [...accepted.value],
  ...form,
}));

// A seção que deve estar na linha de foco agora: a escolha conduz o cadastro.
const activeSection = ref<string | null>("intent");

function changeIntent() {
  intent.value = "";
  activeSection.value = "intent";
}

watch(
  () => [props.open, props.mode, props.suggestedSku, props.suggestedName],
  () => {
    if (props.open) {
      resetForm();
      activeSection.value = "intent";
      capture();
    }
  },
  { immediate: true },
);

// O rascunho chega e preenche o que ainda está vazio. Marcar o campo habilita o
// aceite; o servidor aplica a partir do rascunho dele, nunca do que veio da tela.
watch(
  () => props.draft,
  (draft) => {
    if (!draft) return;
    accepted.value = new Set(Object.keys(draft.fields));
    const value = (name: string) => draft.fields[name]?.value;
    if (!form.name && typeof value("name") === "string")
      form.name = value("name") as string;
    if (form.unit_weight_g === "" && typeof value("net_weight_g") === "number")
      form.unit_weight_g = String(value("net_weight_g"));
    if (!form.ingredients_text && typeof value("ingredients_text") === "string")
      form.ingredients_text = value("ingredients_text") as string;
    if (
      (!form.unit || form.unit === "un") &&
      typeof value("fiscal_unit") === "string"
    )
      form.unit = String(value("fiscal_unit")).toLowerCase();
    activeSection.value = "draft";
  },
);

// Lista com a ENTRADA já resolvida: iterar as chaves e indexar de novo deixava o
// campo "possivelmente undefined" para o typecheck.
const draftFields = computed(() =>
  Object.entries(props.draft?.fields ?? {}).map(([name, entry]) => ({
    name,
    entry,
  })),
);

function parseBrl(text: string): number | null {
  const clean = text
    .replace(/[^\d,.-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  if (!clean) return null;
  const value = Number(clean);
  return Number.isFinite(value) ? Math.round(value * 100) : null;
}

const priceQ = computed(() => parseBrl(form.priceText));
const valid = computed(
  () =>
    form.sku.trim() !== "" &&
    form.name.trim() !== "" &&
    (isDuplicate.value || (priceQ.value !== null && priceQ.value >= 0)),
);

// Como o cadastro conduz: escolher a intenção leva o foco à próxima seção e o
// botão do topo troca de volta.
function chooseIntent(value: "revenda" | "producao" | "insumo") {
  intent.value = value;
  if (value !== "insumo") activeSection.value = "gtin";
}

const saveLabel = computed(() => {
  if (!isDuplicate.value && intent.value === "insumo") return "Abrir o Compras";
  return isDuplicate.value ? "Duplicar" : "Criar produto";
});

const saveDisabled = computed(() =>
  !isDuplicate.value && intent.value === "insumo" ? false : !valid.value,
);

const saveDisabledReason = computed(() => {
  if (!isDuplicate.value && intent.value === "")
    return "Escolha o que você vai cadastrar.";
  if (!isDuplicate.value && intent.value === "insumo") return "";
  const missing: string[] = [];
  if (!form.sku.trim()) missing.push("o código");
  if (!form.name.trim()) missing.push("o nome");
  if (!isDuplicate.value && priceQ.value === null) missing.push("o preço");
  if (!missing.length) return "Confira os campos obrigatórios para salvar.";
  if (missing.length === 1) return `Informe ${missing[0]} para salvar.`;
  const last = missing.pop() as string;
  return `Informe ${missing.join(", ")} e ${last} para salvar.`;
});

const saveAttrs = computed(() => ({
  "data-testid":
    !isDuplicate.value && intent.value === "insumo"
      ? "create-go-purchase"
      : "create-submit",
}));
const discardAttrs = { "data-testid": "create-discard" } as const;

function lookup() {
  if (gtin.value.trim()) emit("lookup", gtin.value.trim());
}

function toggleField(name: string, checked: boolean) {
  const next = new Set(accepted.value);
  if (checked) next.add(name);
  else next.delete(name);
  accepted.value = next;
}

function useSuggestion(suggestion: CorrelateResult["suggestions"][number]) {
  if (suggestion.field === "fiscal_profile") {
    form.fiscal_profile = String(suggestion.value);
    return;
  }
  if (suggestion.field === "shelf_life_days") {
    form.shelf_life_days = String(suggestion.value);
    return;
  }
  if (suggestion.field === "is_batch_produced") {
    form.is_batch_produced = Boolean(suggestion.value);
    return;
  }
  if (
    suggestion.field === "unit" ||
    suggestion.field === "availability_policy"
  ) {
    (form as Record<string, unknown>)[suggestion.field] = String(
      suggestion.value,
    );
  }
}

async function onPhotoPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  photoResult.value = "";
  photoOriginal.value = "";
  uploadedUrl.value = "";
  photoError.value = "";
  if (file.size > 8 * 1024 * 1024) {
    photoError.value = "A foto é grande demais (máximo 8 MB).";
    return;
  }
  photoOriginal.value = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("read_failed"));
    reader.readAsDataURL(file);
  });
  photoBusy.value = true;
  try {
    photoResult.value = await props.enhance(photoOriginal.value);
  } catch (error) {
    // O ajuste é conveniência: sem ele a foto original ainda pode ser usada.
    photoError.value = httpErrorMessage(
      error,
      "Não foi possível padronizar a foto. A original ainda pode ser usada.",
    );
  } finally {
    photoBusy.value = false;
  }
}

async function usePhoto() {
  const image = photoResult.value || photoOriginal.value;
  if (!image) return;
  photoError.value = "";
  uploadBusy.value = true;
  try {
    uploadedUrl.value = await props.upload(image);
    form.image_url = uploadedUrl.value;
  } catch (error) {
    photoError.value = httpErrorMessage(
      error,
      "Não foi possível guardar a foto agora. A tela segue sem ela.",
    );
  } finally {
    uploadBusy.value = false;
  }
}

function submit() {
  if (!isDuplicate.value && intent.value === "insumo") {
    emit("go-purchase");
    return;
  }
  if (!valid.value) return;
  const payload: CreateProductPayload = {
    sku: form.sku.trim(),
    name: form.name.trim(),
    base_price_q: priceQ.value ?? undefined,
    unit: form.unit.trim() || "un",
    short_description: form.short_description.trim(),
    long_description: form.long_description.trim(),
    keywords: form.keywordsText
      .split(",")
      .map((word) => word.trim())
      .filter(Boolean),
    image_url: form.image_url.trim(),
    availability_policy: form.availability_policy,
    storage_tip: form.storage_tip.trim(),
    ingredients_text: form.ingredients_text.trim(),
    is_published: form.is_published,
    is_sellable: form.is_sellable,
    is_batch_produced: form.is_batch_produced,
  };
  if (form.unit_weight_g !== "")
    payload.unit_weight_g = Number(form.unit_weight_g);
  if (form.shelf_life_days !== "")
    payload.shelf_life_days = Number(form.shelf_life_days);
  if (form.fiscal_profile) payload.fiscal = { profile: form.fiscal_profile };
  if (!isDuplicate.value) {
    payload.intent = intent.value || undefined;
    payload.purchase =
      intent.value === "revenda" ? linkPurchase.value : undefined;
  }
  if (!isDuplicate.value && gtin.value.trim()) {
    // O aceite é sempre explícito: só os campos marcados vão, e a marcação é a
    // confirmação para sobrepor o que o formulário trouxe.
    payload.enrichment = {
      gtin: gtin.value.trim(),
      accept: [...accepted.value],
      replace: [...accepted.value],
    };
  }
  emit("save", payload);
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="title"
    :description="subtitle"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="saveLabel"
    :save-disabled="saveDisabled"
    :save-disabled-reason="saveDisabledReason"
    :active-section="activeSection"
    :save-attrs="saveAttrs"
    :discard-attrs="discardAttrs"
    @update:open="(value: boolean) => emit('update:open', value)"
    @save="submit"
  >
    <template #lead>
      <NuxtButton
        v-if="!isDuplicate && intent"
        color="neutral"
        variant="ghost"
        label="Trocar intenção"
        @click="changeIntent"
      />
    </template>
    <template #default>
      <div class="flex flex-col gap-4">
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :description="error"
        />
        <NuxtAlert
          v-if="isDuplicate"
          color="info"
          variant="subtle"
          icon="i-lucide-copy"
          title="O que a cópia traz"
          :description="duplicateNote"
        />

        <!-- Intenção PRIMEIRO: ela diz o que o cadastro é e conduz o caminho. -->
        <OperatorFormSection section-key="intent">
          <NuxtCard v-if="!isDuplicate && !intent" variant="soft">
            <div class="flex flex-col gap-2">
              <p class="text-sm font-medium">O que você vai cadastrar?</p>
              <NuxtButton
                v-for="option in intents"
                :key="option.value"
                color="neutral"
                variant="outline"
                class="w-full justify-start"
                :data-intent="option.value"
                @click="chooseIntent(option.value)"
              >
                <span class="block text-left">
                  <span class="block text-sm font-medium">{{
                    option.label
                  }}</span>
                  <span class="block text-xs text-muted-foreground">{{
                    option.help
                  }}</span>
                </span>
              </NuxtButton>
            </div>
          </NuxtCard>
          <NuxtCard v-if="!isDuplicate && intent === 'insumo'" variant="soft">
            <p class="text-sm font-medium">Só compro (insumo)</p>
            <p class="text-xs text-muted-foreground">
              Insumo não entra no catálogo: o cadastro de compra é no Compras,
              com fornecedor, custo e conversão. Nada é criado aqui.
            </p>
          </NuxtCard>
        </OperatorFormSection>

        <OperatorFormSection
          v-if="!isDuplicate && intent !== '' && intent !== 'insumo'"
          section-key="gtin"
        >
          <NuxtCard variant="soft">
            <div class="flex flex-col gap-3">
              <div class="flex flex-wrap items-end gap-2">
                <NuxtFormField
                  label="Código de barras (GTIN)"
                  class="min-w-48 flex-1"
                >
                  <NuxtInput
                    v-model="gtin"
                    inputmode="numeric"
                    placeholder="7891000053508"
                    data-testid="create-gtin"
                    data-focus-control
                    @keyup.enter="lookup"
                  />
                </NuxtFormField>
                <NuxtButton
                  icon="i-lucide-scan-barcode"
                  label="Ler"
                  color="neutral"
                  variant="outline"
                  data-testid="create-scan"
                  @click="scanner.start()"
                />
                <NuxtButton
                  label="Buscar dados"
                  :loading="draftBusy"
                  :disabled="!gtin.trim()"
                  data-testid="create-lookup"
                  @click="lookup"
                />
              </div>
              <p v-if="scanner.error.value" class="text-xs text-error">
                {{ scanner.error.value }}
              </p>
              <p v-if="draftError" class="text-xs text-error">
                {{ draftError }}
              </p>
              <p class="text-xs text-muted-foreground">
                O código lido preenche o rascunho com o que as fontes sabem.
                Nada é gravado até você salvar.
              </p>
            </div>
          </NuxtCard>
        </OperatorFormSection>

        <OperatorFormSection
          v-if="!isDuplicate && draft && intent !== 'insumo'"
          section-key="draft"
        >
          <NuxtCard variant="outline">
            <div class="flex flex-col gap-3">
              <p class="text-sm font-medium">Revise o que as fontes trazem</p>
              <label
                v-for="item in draftFields"
                :key="item.name"
                class="flex items-start gap-2"
              >
                <NuxtCheckbox
                  :model-value="accepted.has(item.name)"
                  class="mt-0.5"
                  @update:model-value="
                    (value: boolean | 'indeterminate') =>
                      toggleField(item.name, value === true)
                  "
                />
                <span class="min-w-0">
                  <span class="block text-sm">
                    {{ item.entry.label }}:
                    {{ item.entry.display }}
                  </span>
                  <span class="block text-xs text-muted-foreground">
                    Fonte: {{ item.entry.source_label }}
                    <template v-if="item.entry.detail">
                      · {{ item.entry.detail }}
                    </template>
                  </span>
                  <span
                    v-for="alternative in item.entry.alternatives ?? []"
                    :key="alternative.source"
                    class="block text-xs text-muted-foreground"
                  >
                    {{ alternative.source }} diz outra coisa:
                    {{ alternative.value }}
                  </span>
                </span>
              </label>
              <p
                v-for="note in draft.notes"
                :key="note"
                class="text-xs text-muted-foreground"
              >
                {{ note }}
              </p>
              <div v-if="draft.reference_photo" class="flex items-start gap-2">
                <img
                  :src="draft.reference_photo.url"
                  :alt="'Foto de referência de ' + draft.fields.name?.value"
                  class="h-16 w-16 rounded object-cover"
                />
                <p class="text-xs text-muted-foreground">
                  Foto de referência ({{ draft.reference_photo.source }},
                  {{ draft.reference_photo.license }}): serve para reconhecer o
                  item, não vai para a vitrine.
                </p>
              </div>
              <div
                v-if="draft.correlate.suggestions.length"
                class="flex flex-col gap-2 border-t border-default pt-3"
              >
                <p class="text-sm font-medium">
                  Reaproveitar de produtos parecidos
                </p>
                <div
                  v-for="suggestion in draft.correlate.suggestions"
                  :key="suggestion.field"
                  class="flex items-center justify-between gap-2"
                >
                  <span class="text-xs">{{ suggestion.reason }}</span>
                  <NuxtButton
                    color="neutral"
                    variant="outline"
                    label="Usar"
                    @click="useSuggestion(suggestion)"
                  />
                </div>
                <p class="text-xs text-muted-foreground">
                  Parecidos:
                  {{
                    draft.correlate.correlates
                      .map((item: { sku: string }) => item.sku)
                      .join(", ")
                  }}
                </p>
              </div>
            </div>
          </NuxtCard>
        </OperatorFormSection>

        <OperatorFormSection
          v-if="!isDuplicate && intent !== '' && intent !== 'insumo'"
          section-key="photo"
        >
          <NuxtCard variant="soft">
            <div class="flex flex-col gap-3">
              <NuxtFormField
                label="Foto do produto"
                hint="Escolha uma imagem para padronizar."
              >
                <NuxtInput
                  type="file"
                  accept="image/*"
                  :disabled="photoBusy"
                  data-testid="create-photo-input"
                  @change="onPhotoPicked"
                />
              </NuxtFormField>
              <p class="text-xs text-muted-foreground">
                O ajuste é determinístico: recorta a borda, enquadra e afina.
                Não inventa o produto.
              </p>
              <p v-if="photoError" class="text-xs text-warning">
                {{ photoError }}
              </p>
              <div
                v-if="photoResult || photoOriginal"
                class="flex items-center gap-3"
              >
                <img
                  :src="photoResult || photoOriginal"
                  alt="Prévia da foto"
                  class="h-20 w-20 rounded object-cover"
                />
                <div class="flex flex-col items-start gap-1">
                  <NuxtButton
                    color="neutral"
                    variant="outline"
                    :label="
                      form.image_url
                        ? 'Foto guardada'
                        : 'Usar como foto do produto'
                    "
                    :loading="uploadBusy"
                    :disabled="Boolean(form.image_url)"
                    data-testid="create-photo-use"
                    @click="usePhoto"
                  />
                  <a
                    v-if="photoResult"
                    :href="photoResult"
                    download="produto.jpg"
                    class="text-xs underline"
                    >Baixar padronizada</a
                  >
                </div>
              </div>
              <p v-if="form.image_url" class="text-xs text-success break-all">
                {{ form.image_url }}
              </p>
            </div>
          </NuxtCard>
        </OperatorFormSection>

        <OperatorFormSection
          v-if="!isDuplicate && intent === 'revenda'"
          section-key="purchase"
        >
          <NuxtCard variant="soft">
            <NuxtCheckbox
              v-model="linkPurchase"
              label="Ligar o comprável do mesmo SKU (Permitir compra)"
            />
            <p class="mt-1 text-xs text-muted-foreground">
              O fornecedor e o custo ficam no Compras; o estoque é o mesmo SKU.
            </p>
          </NuxtCard>
        </OperatorFormSection>
        <OperatorFormSection
          v-if="!isDuplicate && intent === 'producao'"
          section-key="production"
        >
          <NuxtCard variant="soft">
            <p class="text-sm font-medium">Produzo e vendo aqui</p>
            <p class="text-xs text-muted-foreground">
              O vendável nasce no catálogo e a ficha de execução entra na
              Produção.
            </p>
            <a
              v-if="adminBaseUrl"
              :href="`${adminBaseUrl}/admin/craftsman/recipe/add/`"
              target="_blank"
              rel="noopener"
              class="mt-1 inline-block text-sm underline"
              >Abrir a ficha no Admin</a
            >
          </NuxtCard>
        </OperatorFormSection>

        <OperatorFormSection
          v-if="isDuplicate || (intent !== '' && intent !== 'insumo')"
          section-key="fields"
          title="Dados do produto"
          description="Preencha o que a loja e a nota vão usar."
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <NuxtFormField label="SKU" required>
              <NuxtInput
                v-model="form.sku"
                data-testid="create-sku"
                data-focus-control
              />
            </NuxtFormField>
            <NuxtFormField label="Nome" required>
              <NuxtInput v-model="form.name" data-testid="create-name" />
            </NuxtFormField>
            <template v-if="!isDuplicate">
              <NuxtFormField label="Preço (R$)">
                <NuxtInput
                  v-model="form.priceText"
                  inputmode="decimal"
                  placeholder="15,00"
                  data-testid="create-price"
                />
              </NuxtFormField>
              <NuxtFormField label="Unidade de venda">
                <NuxtInput v-model="form.unit" placeholder="un" />
              </NuxtFormField>
              <NuxtFormField label="Descrição curta" class="sm:col-span-2">
                <NuxtInput v-model="form.short_description" />
              </NuxtFormField>
              <NuxtFormField label="Descrição longa" class="sm:col-span-2">
                <NuxtTextarea v-model="form.long_description" :rows="3" />
              </NuxtFormField>
              <NuxtFormField label="Palavras-chave" hint="Separe por vírgula.">
                <NuxtInput v-model="form.keywordsText" />
              </NuxtFormField>
              <NuxtFormField label="URL da imagem">
                <NuxtInput v-model="form.image_url" placeholder="https://" />
              </NuxtFormField>
              <NuxtFormField label="Política de disponibilidade">
                <NuxtSelect
                  v-model="form.availability_policy"
                  :items="policyOptions"
                />
              </NuxtFormField>
              <NuxtFormField label="Validade (dias)">
                <NuxtInput
                  v-model="form.shelf_life_days"
                  inputmode="numeric"
                  placeholder="Vazio = não perecível"
                />
              </NuxtFormField>
              <NuxtFormField label="Peso por unidade (g)">
                <NuxtInput v-model="form.unit_weight_g" inputmode="numeric" />
              </NuxtFormField>
              <NuxtFormField label="Dica de conservação">
                <NuxtInput v-model="form.storage_tip" />
              </NuxtFormField>
              <NuxtFormField label="Ingredientes" class="sm:col-span-2">
                <NuxtTextarea v-model="form.ingredients_text" :rows="2" />
              </NuxtFormField>
              <div class="flex items-center gap-4 sm:col-span-2">
                <NuxtCheckbox
                  v-model="form.is_published"
                  label="Exibido no catálogo"
                />
                <NuxtCheckbox
                  v-model="form.is_sellable"
                  label="Disponível para venda"
                />
              </div>
            </template>
          </div>
        </OperatorFormSection>
      </div>
    </template>
  </OperatorFormShell>

  <NuxtModal
    :open="scanner.open.value"
    title="Ler código de barras"
    @update:open="
      (value: boolean) => {
        if (!value) scanner.stop();
      }
    "
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <video
          :ref="
            (el) => {
              scanner.video.value = el as HTMLVideoElement | null;
            }
          "
          class="w-full rounded-lg"
          playsinline
          muted
        />
        <p class="text-sm text-muted-foreground">{{ scanner.hint.value }}</p>
      </div>
    </template>
  </NuxtModal>
</template>
