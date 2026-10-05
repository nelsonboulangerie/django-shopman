<script setup lang="ts">
// Avisos deste dispositivo. Montado hoje só na home (Central), que é onde o
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
//
// Duas formas (`variant`), o mesmo mecanismo e as mesmas frases de causa:
//   - `card` (padrão): o bloco inteiro, com o que chega e os dispositivos à vista;
//   - `line` (Central na camada da suíte, prévia v4 `hub4.html`): a linha calma do rodapé,
//     "Avisos neste dispositivo: <estado>" com o gesto que cabe ao estado (ativar aqui
//     mesmo, ou abrir o que chega e os dispositivos logo abaixo). Nada some: o mesmo
//     conteúdo do cartão fica a um toque. O slot `end` recebe o que divide a linha (a
//     versão do build, na Central).
import { OPERATOR_APPS, operatorAppNamed } from "../../appIdentity";

const props = withDefaults(defineProps<{ variant?: "card" | "line" }>(), { variant: "card" });

const {
  supported, unavailableReason, active, permission, loading, error, devices, categories,
  currentDevice, activate, updateCategories, removeDevice,
} = useWebPush();

/** "a Central", com o artigo da identidade: a frase não congela o gênero do rótulo. */
const hubNamed = operatorAppNamed("hub");
const hubNamedOf = operatorAppNamed("hub", "de");

/** `surface_ref` é chave de API ("hub", "pos"). Na tela vai o nome do app. */
function surfaceLabel(ref: string): string {
  return OPERATOR_APPS[ref as keyof typeof OPERATOR_APPS]?.label || ref;
}

/** A linha (`variant="line"`): o estado em poucas palavras, a causa inteira quando falta algo. */
const canActivate = computed(() => permission.value !== "denied" && supported.value && !active.value);
const hasDetails = computed(() => Boolean(currentDevice.value) || devices.value.length > 0);
const detailsOpen = ref(false);
const lineState = computed(() => {
  if (permission.value === "denied") {
    return "este navegador está bloqueando os avisos deste site. Libere a permissão de notificações nos ajustes do site e recarregue esta tela.";
  }
  if (active.value) return "ligados. Chegam mesmo com a janela fechada.";
  if (supported.value) return `desligados. Ligue para receber mesmo com a janela ${hubNamedOf} fechada.`;
  if (unavailableReason.value === "deploy") {
    return "o envio ainda não foi configurado nesta instalação. Peça a quem cuida do sistema.";
  }
  if (unavailableReason.value === "browser") {
    return `este navegador não entrega avisos com o app fechado. No iPhone e no iPad, adicione ${hubNamed} à Tela de Início (Compartilhar › Adicionar à Tela de Início) e ative por lá.`;
  }
  return "";
});

async function updateCategorySelection(next: string[]): Promise<void> {
  const device = currentDevice.value;
  if (!device) return;
  await updateCategories(device, next);
}
</script>

<template>
  <section
    data-hub-push-settings
    :data-variant="props.variant"
    :class="props.variant === 'line' ? 'grid gap-2' : 'mt-6 rounded-xl border border-border bg-card p-4'"
  >
    <template v-if="props.variant === 'line'">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 op-label font-normal text-muted-foreground">
        <Icon :name="active ? 'lucide:bell' : 'lucide:bell-off'" class="size-4 shrink-0" aria-hidden="true" />
        <ClientOnly>
          <span class="min-w-0" role="status" data-push-line-state :data-push-unavailable="unavailableReason || undefined">
            Avisos neste dispositivo<template v-if="lineState">: {{ lineState }}</template>
          </span>
          <button
            v-if="canActivate"
            type="button"
            data-activate-push
            class="inline-flex min-h-control items-center font-semibold text-foreground underline decoration-border underline-offset-4 disabled:opacity-60"
            :disabled="loading"
            @click="activate"
          >
            {{ loading ? 'Ativando…' : 'Ativar neste dispositivo' }}
          </button>
          <button
            v-else-if="hasDetails"
            type="button"
            data-push-details-toggle
            class="inline-flex min-h-control items-center font-semibold text-foreground underline decoration-border underline-offset-4"
            :aria-expanded="detailsOpen"
            aria-controls="push-settings-details"
            @click="detailsOpen = !detailsOpen"
          >
            {{ detailsOpen ? 'Fechar' : currentDevice ? 'Escolher o que chega' : 'Ver dispositivos' }}
          </button>
          <template #fallback>
            <span class="min-w-0">Avisos neste dispositivo</span>
          </template>
        </ClientOnly>
        <slot name="end" />
      </div>
      <p v-if="error" role="status" class="op-label font-normal text-destructive">{{ error }}</p>
    </template>

    <template v-else>
      <h2 class="text-base font-semibold">Avisos neste dispositivo</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Avisos da operação chegam a este dispositivo mesmo com a janela {{ hubNamedOf }} fechada.
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
        sistema para ligá-lo. Enquanto isso, nenhum dispositivo recebe aviso.
      </p>
      <p v-else-if="unavailableReason === 'browser'" role="status" data-push-unavailable="browser" class="mt-4 text-sm text-muted-foreground">
        Este navegador não entrega avisos com o app fechado. No iPhone e no iPad, adicione
        {{ hubNamed }} à Tela de Início (botão Compartilhar › Adicionar à Tela de Início) e
        ative os avisos por lá.
      </p>
      <p v-if="error" role="status" class="mt-2 text-sm text-destructive">{{ error }}</p>
    </template>

    <div
      v-if="props.variant === 'card' || detailsOpen"
      id="push-settings-details"
      :class="props.variant === 'line' ? 'rounded-xl border border-border bg-card px-4 pb-4' : ''"
      data-push-details
    >
      <div v-if="currentDevice" :class="props.variant === 'line' ? 'pt-4' : 'mt-5 border-t border-border pt-4'">
        <UiCheckboxGroup
          :model-value="currentDevice.categories"
          :items="categories"
          legend="O que chega aqui"
          variant="card"
          orientation="horizontal"
          :ui="{
            fieldset: 'mt-3 gap-2',
            legend: 'text-sm font-semibold',
            item: 'min-w-0 basis-full sm:basis-[calc(50%-0.25rem)]',
          }"
          @update:model-value="updateCategorySelection"
        />
      </div>

      <div v-if="devices.length" :class="props.variant === 'line' && !currentDevice ? 'pt-4' : 'mt-5 border-t border-border pt-4'">
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
    </div>
  </section>
</template>
