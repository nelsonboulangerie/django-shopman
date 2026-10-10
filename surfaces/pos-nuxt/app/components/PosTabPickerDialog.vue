<script setup lang="ts">
import type { POSTabProjection } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  tabs: POSTabProjection[];
  modelValue: string;
  busy: boolean;
  hasDraft: boolean;
  allowedTargetStates: string[];
  title: string;
  description: string;
  maxLength: number;
  placeholder: string;
  disallowedChars: string[];
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:modelValue": [string];
  confirm: [string];
  select: [POSTabProjection];
}>();

const normalizedQuery = computed(() => props.modelValue.trim().toLowerCase());
const filteredTabs = computed(() => {
  const query = normalizedQuery.value;
  return props.tabs.filter((tab) => {
    if (!query) return true;
    return [
      tab.display_ref,
      tab.ref,
      tab.customer_name,
      tab.customer_phone,
      tab.items_preview,
      tab.status_label,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  });
});

function sanitizeTabRef(value: string): string {
  const disallowed = new Set(props.disallowedChars || []);
  return value
    .replace(/[\r\n\t]/g, "")
    .split("")
    .filter((char) => !disallowed.has(char))
    .join("")
    .replace(/\s+/g, " ")
    .slice(0, props.maxLength || 64);
}

function updateValue(value: unknown) {
  emit("update:modelValue", sanitizeTabRef(String(value || "")));
}

function canAssociate(tab: POSTabProjection): boolean {
  if (!props.hasDraft) return true;
  return props.allowedTargetStates.includes(tab.state);
}

function selectTab(tab: POSTabProjection) {
  if (!canAssociate(tab)) return;
  emit("select", tab);
}

function confirmTyped() {
  const code = sanitizeTabRef(props.modelValue);
  if (!code) return;
  emit("confirm", code);
}
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    :description="description"
    :ui="{ content: 'sm:max-w-xl' }"
    data-pos-tab-picker
    @update:open="$emit('update:open', Boolean($event))"
  >
    <template #body>
      <div class="grid gap-4">
      <form class="grid gap-2" @submit.prevent="confirmTyped">
        <label class="grid gap-1 text-xs">
          <span class="font-medium text-muted-foreground">Referência da comanda</span>
          <div class="flex gap-2">
            <UiInput
              :model-value="modelValue"
              :maxlength="maxLength"
              :placeholder="placeholder"
              autofocus
              @update:model-value="updateValue"
            />
            <NuxtButton type="submit" color="primary" label="Abrir comanda" :disabled="busy || !modelValue.trim()" />
          </div>
        </label>
      </form>

      <div class="grid gap-2">
        <div class="flex items-center justify-between gap-2">
          <p class="text-sm font-medium text-muted-foreground">Comandas salvas</p>
          <UiBadge v-if="hasDraft" variant="outline">Rascunho atual</UiBadge>
        </div>
        <div v-if="filteredTabs.length" class="grid max-h-72 gap-2 overflow-auto pr-1 sm:grid-cols-2">
          <NuxtButton
            v-for="tab in filteredTabs"
            :key="tab.ref"
            color="neutral"
            variant="outline"
            class="justify-normal grid gap-1 px-3 py-2 text-left font-normal"
            :class="tab.state === 'in_use' ? 'bg-warning/10' : ''"
            :disabled="busy || !canAssociate(tab)"
            @click="selectTab(tab)"
          >
            <span class="font-semibold tabular-nums">#{{ tab.display_ref }}</span>
            <span class="text-xs text-muted-foreground">{{ tab.status_label }}</span>
            <span v-if="tab.item_count" class="text-xs font-semibold tabular-nums">
              {{ tab.item_count }} · {{ tab.total_display }}
            </span>
            <span v-if="hasDraft && !canAssociate(tab)" class="text-xs text-warning">
              Abra separadamente para evitar mistura de pedidos.
            </span>
          </NuxtButton>
        </div>
        <p v-else class="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
          Nenhuma comanda encontrada. Digite uma referência para abrir uma nova.
        </p>
      </div>

      </div>
    </template>
    <template #footer>
      <NuxtButton
        class="ml-auto"
        color="neutral"
        variant="outline"
        label="Cancelar"
        :disabled="busy"
        @click="$emit('update:open', false)"
      />
    </template>
  </NuxtModal>
</template>
