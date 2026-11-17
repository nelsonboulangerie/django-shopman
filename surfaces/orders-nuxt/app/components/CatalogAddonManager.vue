<script setup lang="ts">
// Complementos de um produto no iFood (homologação do Catalog, cenários 2 e 3).
// Cada gesto grava aqui e só fica quando o iFood confirma pela leitura do item;
// a faixa de confirmação diz o que o iFood confirmou e a hora.
import { formatBRL } from "../../../operator-kit/app/utils/money";
import {
  addonStatusLabel,
  choiceRule,
  parsePriceQ,
  splitIfoodReason,
} from "~/presentation/channelAddons";
import type { ChannelAddon } from "~/composables/useChannelAddons";

const props = defineProps<{ channel: string }>();
const {
  sku,
  board,
  pending,
  error,
  busy,
  receipt,
  clockNow,
  uploadPhoto,
  createGroup,
  addAddon,
  editAddon,
  changePrice,
  setActive,
} = useChannelAddons(props.channel);

const productItems = computed(() =>
  (board.value?.products ?? []).map((product) => ({
    label: product.name,
    value: product.sku,
  })),
);
const blocked = computed(
  () => busy.value || !board.value?.action.enabled || Boolean(error.value),
);

// Novo grupo
const groupDraft = reactive({ open: false, name: "", min: 0, max: 1 });
async function submitGroup() {
  if (
    await createGroup(
      groupDraft.name.trim(),
      Number(groupDraft.min),
      Number(groupDraft.max),
    )
  )
    Object.assign(groupDraft, { open: false, name: "", min: 0, max: 1 });
}

// Novo complemento (por grupo)
const addonDraft = reactive<{
  group: number | null;
  name: string;
  price: string;
  file: File | null;
  uploading: boolean;
}>({ group: null, name: "", price: "", file: null, uploading: false });
const addonPriceQ = computed(() => parsePriceQ(addonDraft.price));
function pickFile(event: Event, target: { file: File | null }) {
  target.file = (event.target as HTMLInputElement).files?.[0] ?? null;
}
async function submitAddon(groupId: number) {
  if (addonPriceQ.value === null || !addonDraft.name.trim()) return;
  addonDraft.uploading = true;
  let imageUrl = "";
  try {
    if (addonDraft.file) imageUrl = await uploadPhoto(addonDraft.file);
  } catch (failure) {
    receipt.value = {
      ok: false,
      message: httpErrorMessage(failure, "Não foi possível guardar a foto."),
      at: clockNow(),
    };
    return;
  } finally {
    addonDraft.uploading = false;
  }
  if (
    await addAddon(groupId, addonDraft.name.trim(), addonPriceQ.value, imageUrl)
  )
    Object.assign(addonDraft, { group: null, name: "", price: "", file: null });
}

// Editar nome e foto (PUT) · preço (PATCH) · pausar/retomar (PATCH)
const editing = reactive<{
  id: number | null;
  mode: "edit" | "price" | null;
  name: string;
  price: string;
  file: File | null;
  uploading: boolean;
}>({ id: null, mode: null, name: "", price: "", file: null, uploading: false });
function startEdit(addon: ChannelAddon, mode: "edit" | "price") {
  Object.assign(editing, {
    id: addon.id,
    mode,
    name: addon.name,
    price: (addon.price_q / 100).toFixed(2).replace(".", ","),
    file: null,
  });
}
function stopEdit() {
  Object.assign(editing, { id: null, mode: null, file: null });
}
const editPriceQ = computed(() => parsePriceQ(editing.price));
async function submitEdit(addon: ChannelAddon) {
  if (!editing.name.trim()) return;
  editing.uploading = true;
  let imageUrl: string | null = null;
  try {
    if (editing.file) imageUrl = await uploadPhoto(editing.file);
  } catch (failure) {
    receipt.value = {
      ok: false,
      message: httpErrorMessage(failure, "Não foi possível guardar a foto."),
      at: clockNow(),
    };
    return;
  } finally {
    editing.uploading = false;
  }
  if (await editAddon(addon.id, editing.name.trim(), imageUrl)) stopEdit();
}
// O giro fica só no complemento que está sendo pausado ou retomado.
const toggling = ref<number | null>(null);
async function toggle(addon: ChannelAddon) {
  toggling.value = addon.id;
  try {
    await setActive(addon.id, !addon.is_active);
  } finally {
    toggling.value = null;
  }
}
async function submitPrice(addon: ChannelAddon) {
  if (editPriceQ.value === null) return;
  if (await changePrice(addon.id, editPriceQ.value)) stopEdit();
}
</script>

<template>
  <section aria-label="Complementos no iFood" data-catalog-addons>
    <NuxtCard variant="outline">
      <div class="space-y-5">
        <div class="max-w-3xl space-y-1">
          <h2 class="op-title">Complementos no iFood</h2>
          <p class="text-sm text-muted-foreground">
            O Catálogo da casa não tem complementos; eles moram no produto do
            canal iFood, com o mesmo SKU, e vão junto com o item.
          </p>
        </div>

        <NuxtFormField label="Produto do canal iFood" class="max-w-md">
          <NuxtSelectMenu
            v-model="sku"
            :items="productItems"
            value-key="value"
            placeholder="Escolha um produto"
            class="w-full"
            :loading="pending"
            :disabled="busy"
            data-addon-product
          />
        </NuxtFormField>

        <NuxtAlert
          v-if="receipt"
          :color="receipt.ok ? 'success' : 'error'"
          variant="subtle"
          :icon="receipt.ok ? 'i-lucide-circle-check' : 'i-lucide-circle-alert'"
          :title="
            receipt.ok
              ? `Gravado no iFood às ${receipt.at}`
              : `O iFood recusou às ${receipt.at}`
          "
          :description="splitIfoodReason(receipt.message).text"
          close
          data-addon-receipt
          @update:open="receipt = null"
        >
          <template
            v-if="!receipt.ok && splitIfoodReason(receipt.message).original"
            #actions
          >
            <p
              class="text-xs text-muted-foreground"
              data-addon-receipt-original
            >
              Resposta do iFood:
              {{ splitIfoodReason(receipt.message).original }}
            </p>
          </template>
        </NuxtAlert>
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Não foi possível ler os complementos"
          description="Atualize a página para tentar de novo."
        />

        <template v-if="sku && board">
          <NuxtEmpty
            v-if="!board.groups.length"
            icon="i-lucide-list-plus"
            title="Este produto ainda não tem complementos"
            description="Crie o primeiro grupo, por exemplo Escolha o acompanhamento."
          />

          <NuxtCard
            v-for="group in board.groups"
            :key="group.id"
            variant="soft"
            as="article"
            :aria-label="group.name"
            data-addon-group
          >
            <div class="space-y-3">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 class="font-semibold">{{ group.name }}</h3>
                  <p class="text-sm text-muted-foreground">
                    {{ choiceRule(group.min_choices, group.max_choices) }}
                  </p>
                </div>
                <NuxtButton
                  v-if="addonDraft.group !== group.id"
                  label="Novo complemento"
                  icon="i-lucide-plus"
                  color="neutral"
                  variant="outline"
                  :disabled="blocked"
                  @click="
                    Object.assign(addonDraft, {
                      group: group.id,
                      name: '',
                      price: '',
                      file: null,
                    })
                  "
                />
              </div>

              <ul class="divide-y divide-default">
                <li
                  v-for="addon in group.addons"
                  :key="addon.id"
                  class="flex flex-wrap items-center gap-3 py-2"
                  data-addon
                >
                  <img
                    v-if="addon.image_url"
                    :src="addon.image_url"
                    :alt="addon.name"
                    class="size-12 rounded-md object-cover"
                  />
                  <div
                    v-else
                    class="grid size-12 place-items-center rounded-md bg-elevated text-muted-foreground"
                  >
                    <NuxtIcon name="i-lucide-image-off" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <p class="font-medium">{{ addon.name }}</p>
                    <p class="text-sm text-muted-foreground">
                      {{ formatBRL(addon.price_q) }}
                    </p>
                  </div>
                  <NuxtBadge
                    :color="addon.is_active ? 'success' : 'neutral'"
                    variant="subtle"
                    :label="addonStatusLabel(addon.is_active)"
                  />
                  <div
                    v-if="editing.id !== addon.id"
                    class="flex flex-wrap gap-1"
                  >
                    <NuxtButton
                      label="Editar nome e foto"
                      icon="i-lucide-pencil"
                      color="neutral"
                      variant="ghost"
                      :disabled="blocked"
                      @click="startEdit(addon, 'edit')"
                    />
                    <NuxtButton
                      label="Alterar preço"
                      icon="i-lucide-badge-dollar-sign"
                      color="neutral"
                      variant="ghost"
                      :disabled="blocked"
                      @click="startEdit(addon, 'price')"
                    />
                    <NuxtButton
                      :label="addon.is_active ? 'Pausar' : 'Retomar'"
                      :icon="
                        addon.is_active ? 'i-lucide-pause' : 'i-lucide-play'
                      "
                      color="neutral"
                      variant="ghost"
                      :loading="busy && toggling === addon.id"
                      :disabled="blocked"
                      @click="toggle(addon)"
                    />
                  </div>
                  <div
                    v-else-if="editing.mode === 'edit'"
                    class="flex w-full flex-wrap items-end gap-2"
                  >
                    <NuxtFormField label="Nome" class="min-w-56 flex-1">
                      <NuxtInput v-model="editing.name" class="w-full" />
                    </NuxtFormField>
                    <NuxtFormField label="Nova foto (JPG ou PNG)">
                      <NuxtInput
                        type="file"
                        accept="image/jpeg,image/png"
                        @change="pickFile($event, editing)"
                      />
                    </NuxtFormField>
                    <NuxtButton
                      label="Enviar ao iFood"
                      :loading="busy || editing.uploading"
                      :disabled="blocked || !editing.name.trim()"
                      @click="submitEdit(addon)"
                    />
                    <NuxtButton
                      label="Cancelar"
                      color="neutral"
                      variant="ghost"
                      :disabled="busy"
                      @click="stopEdit"
                    />
                  </div>
                  <div v-else class="flex w-full flex-wrap items-end gap-2">
                    <NuxtFormField
                      label="Preço (R$)"
                      :error="
                        editing.price && editPriceQ === null
                          ? 'Use o formato 12,50'
                          : false
                      "
                    >
                      <NuxtInput
                        v-model="editing.price"
                        inputmode="decimal"
                        class="w-32"
                      />
                    </NuxtFormField>
                    <NuxtButton
                      label="Enviar ao iFood"
                      :loading="busy"
                      :disabled="blocked || editPriceQ === null"
                      @click="submitPrice(addon)"
                    />
                    <NuxtButton
                      label="Cancelar"
                      color="neutral"
                      variant="ghost"
                      :disabled="busy"
                      @click="stopEdit"
                    />
                  </div>
                </li>
              </ul>

              <div
                v-if="addonDraft.group === group.id"
                class="flex flex-wrap items-end gap-2 rounded-md border border-default p-3"
                data-addon-new
              >
                <NuxtFormField
                  label="Nome do complemento"
                  class="min-w-56 flex-1"
                >
                  <NuxtInput v-model="addonDraft.name" class="w-full" />
                </NuxtFormField>
                <NuxtFormField
                  label="Preço (R$)"
                  :error="
                    addonDraft.price && addonPriceQ === null
                      ? 'Use o formato 12,50'
                      : false
                  "
                >
                  <NuxtInput
                    v-model="addonDraft.price"
                    inputmode="decimal"
                    class="w-32"
                  />
                </NuxtFormField>
                <NuxtFormField label="Foto (JPG ou PNG)">
                  <NuxtInput
                    type="file"
                    accept="image/jpeg,image/png"
                    @change="pickFile($event, addonDraft)"
                  />
                </NuxtFormField>
                <NuxtButton
                  label="Criar no iFood"
                  :loading="busy || addonDraft.uploading"
                  :disabled="
                    blocked || !addonDraft.name.trim() || addonPriceQ === null
                  "
                  @click="submitAddon(group.id)"
                />
                <NuxtButton
                  label="Cancelar"
                  color="neutral"
                  variant="ghost"
                  :disabled="busy"
                  @click="addonDraft.group = null"
                />
              </div>
            </div>
          </NuxtCard>

          <div
            v-if="groupDraft.open"
            class="flex flex-wrap items-end gap-2"
            data-addon-group-new
          >
            <NuxtFormField label="Nome do grupo" class="min-w-56 flex-1">
              <NuxtInput v-model="groupDraft.name" class="w-full" />
            </NuxtFormField>
            <NuxtFormField label="Mínimo">
              <NuxtInput
                v-model.number="groupDraft.min"
                type="number"
                min="0"
                max="99"
                class="w-24"
              />
            </NuxtFormField>
            <NuxtFormField label="Máximo">
              <NuxtInput
                v-model.number="groupDraft.max"
                type="number"
                min="1"
                max="99"
                class="w-24"
              />
            </NuxtFormField>
            <NuxtButton
              label="Criar grupo"
              :loading="busy"
              :disabled="blocked || !groupDraft.name.trim()"
              @click="submitGroup"
            />
            <NuxtButton
              label="Cancelar"
              color="neutral"
              variant="ghost"
              :disabled="busy"
              @click="groupDraft.open = false"
            />
          </div>
          <NuxtButton
            v-else
            label="Novo grupo de complementos"
            icon="i-lucide-list-plus"
            color="neutral"
            variant="outline"
            :disabled="blocked"
            @click="groupDraft.open = true"
          />
        </template>
      </div>
    </NuxtCard>
  </section>
</template>
