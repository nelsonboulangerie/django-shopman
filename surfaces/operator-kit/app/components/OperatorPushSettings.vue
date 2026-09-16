<script setup lang="ts">
const {
  supported, active, permission, loading, error, devices, categories,
  currentDevice, activate, updateCategories, removeDevice,
} = useWebPush();
const runtime = useRuntimeConfig().public as Record<string, unknown>;
const appVersion = String(runtime.appVersion || "local");

function checked(category: string): boolean {
  return currentDevice.value?.categories.includes(category) === true;
}

async function toggleCategory(category: string): Promise<void> {
  const device = currentDevice.value;
  if (!device) return;
  const next = checked(category)
    ? device.categories.filter(value => value !== category)
    : [...device.categories, category];
  await updateCategories(device, next);
}
</script>

<template>
  <section data-hub-push-settings class="mt-6 rounded-xl border border-border bg-card p-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h2 class="text-base font-semibold">Avisos neste aparelho</h2>
        <p class="mt-1 text-sm text-muted-foreground">Receba só alertas operacionais, mesmo com a Central fechada.</p>
      </div>
      <span class="shrink-0 text-xs text-muted-foreground">{{ appVersion }}</span>
    </div>

    <p v-if="permission === 'denied'" role="status" class="mt-4 text-sm text-muted-foreground">
      Os avisos estão bloqueados no navegador. Libere-os nos ajustes deste site.
    </p>
    <button
      v-else-if="supported && !active"
      type="button"
      data-activate-push
      class="mt-4 inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
      :disabled="loading"
      @click="activate"
    >
      {{ loading ? 'Ativando…' : 'Ativar avisos' }}
    </button>
    <p v-else-if="!supported" role="status" data-push-unavailable class="mt-4 text-sm text-muted-foreground">
      Avisos em segundo plano ainda não estão disponíveis neste ambiente. No iPhone, use a Central instalada na Tela de Início.
    </p>
    <p v-if="error" role="status" class="mt-2 text-sm text-destructive">{{ error }}</p>

    <fieldset v-if="currentDevice" class="mt-5 border-t border-border pt-4">
      <legend class="text-sm font-semibold">O que chega aqui</legend>
      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <label v-for="category in categories" :key="category.value" class="flex items-center gap-2 text-sm">
          <input type="checkbox" :checked="checked(category.value)" @change="toggleCategory(category.value)">
          <span>{{ category.label }}</span>
        </label>
      </div>
    </fieldset>

    <div v-if="devices.length" class="mt-5 border-t border-border pt-4">
      <h3 class="text-sm font-semibold">Aparelhos ativos</h3>
      <ul class="mt-2 divide-y divide-border">
        <li v-for="device in devices" :key="device.id" class="flex items-center justify-between gap-3 py-2 text-sm">
          <span class="min-w-0">
            <span class="block truncate font-medium">{{ device.device_label }}</span>
            <span class="block text-xs text-muted-foreground">{{ device.surface_ref }}</span>
          </span>
          <button type="button" class="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline" @click="removeDevice(device)">
            Remover
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
