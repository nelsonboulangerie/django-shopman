<script setup lang="ts">
// Avisos deste dispositivo. Montado hoje só na home (Shopman Apps), que é onde o
// operador administra o que chega a ele.
//
// ⚠️ Este bloco já disse três coisas que ninguém conseguia usar, e as três eram de
// redação, não de mecanismo:
//   1. o carimbo da versão do build ("local") ficava colado no título dos avisos e se
//      lia como um selo do recurso — saiu daqui e foi para o rodapé da home, com rótulo;
//   2. "Receba só alertas operacionais" não dizia o que chega nem quando;
//   3. UMA frase cobria duas causas opostas — instalação sem chave de envio e navegador
//      que não entrega aviso com o app fechado. Agora cada causa tem a sua, porque
//      `useWebPush` sabe distingui-las (`unavailableReason`).
import { OPERATOR_APPS } from "../../appIdentity";

const {
  supported, unavailableReason, active, permission, loading, error, devices, categories,
  currentDevice, activate, updateCategories, removeDevice,
} = useWebPush();

const hubName = OPERATOR_APPS.hub.label;

/** `surface_ref` é chave de API ("hub", "pos"). Na tela vai o nome do app. */
function surfaceLabel(ref: string): string {
  return OPERATOR_APPS[ref as keyof typeof OPERATOR_APPS]?.label || ref;
}

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
    <h2 class="text-base font-semibold">Avisos neste dispositivo</h2>
    <p class="mt-1 text-sm text-muted-foreground">
      Avisos da operação chegam a este dispositivo mesmo com o {{ hubName }} fechado.
    </p>

    <p v-if="permission === 'denied'" role="status" class="mt-4 text-sm text-muted-foreground">
      Este navegador está bloqueando os avisos deste site. Libere a permissão de notificações
      nos ajustes do site e recarregue esta tela.
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
    <p v-else-if="unavailableReason === 'deploy'" role="status" data-push-unavailable="deploy" class="mt-4 text-sm text-muted-foreground">
      O envio de avisos ainda não foi configurado nesta instalação. Peça a quem cuida do
      sistema para ligá-lo — enquanto isso, nenhum dispositivo recebe aviso.
    </p>
    <p v-else-if="unavailableReason === 'browser'" role="status" data-push-unavailable="browser" class="mt-4 text-sm text-muted-foreground">
      Este navegador não entrega avisos com o app fechado. No iPhone e no iPad, adicione o
      {{ hubName }} à Tela de Início (botão Compartilhar › Adicionar à Tela de Início) e
      ative os avisos por lá.
    </p>
    <p v-if="error" role="status" class="mt-2 text-sm text-destructive">{{ error }}</p>

    <fieldset v-if="currentDevice" class="mt-5 border-t border-border pt-4">
      <legend class="text-sm font-semibold">O que chega aqui</legend>
      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <UiCheckbox
          v-for="category in categories"
          :key="category.value"
          :model-value="checked(category.value)"
          :label="category.label"
          @update:model-value="toggleCategory(category.value)"
        />
      </div>
    </fieldset>

    <div v-if="devices.length" class="mt-5 border-t border-border pt-4">
      <h3 class="text-sm font-semibold">Dispositivos que recebem estes avisos</h3>
      <ul class="mt-2 divide-y divide-border">
        <li v-for="device in devices" :key="device.id" class="flex items-center justify-between gap-3 py-2 text-sm">
          <span class="min-w-0">
            <span class="block truncate font-medium">{{ device.device_label }}</span>
            <span class="block text-xs text-muted-foreground">{{ surfaceLabel(device.surface_ref) }}</span>
          </span>
          <button type="button" class="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline" @click="removeDevice(device)">
            Remover
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
