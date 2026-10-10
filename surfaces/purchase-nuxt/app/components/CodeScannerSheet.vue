<script setup lang="ts">
// A câmera do receber em folha de baixo (NuxtDrawer): "Ler EAN", "Bipar cada volume" e "Ler da
// embalagem" usam esta mesma folha (useCodeScanner). Em modo contínuo ela fica
// aberta e conta as leituras; nos outros, fecha na primeira.
import { useCodeScanner } from "~/composables/useCodeScanner";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    /** O que enquadrar ("o código de barras de cada caixa"). */
    hint: string;
    continuous?: boolean;
    /** Modo contínuo: a contagem que a folha mostra ("3 de 9 volumes"). */
    progress?: string;
  }>(),
  { continuous: false, progress: "" },
);
const emit = defineEmits<{
  "update:open": [boolean];
  code: [string];
}>();

const scanner = useCodeScanner((text) => emit("code", text), { continuous: props.continuous });

watch(
  () => props.open,
  (now) => {
    if (now) void scanner.start();
    else scanner.stop();
  },
);
onBeforeUnmount(() => scanner.stop());
</script>

<template>
  <NuxtDrawer
    :open="open"
    direction="bottom"
    :title="title"
    :description="hint"
    close
    class="max-h-[92dvh]"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <template #body>
      <div class="flex flex-col gap-3" :data-code-scanner="title">
        <div class="relative grid aspect-[4/3] w-full place-items-center overflow-hidden rounded-xl bg-black">
          <video
            :ref="(el) => (scanner.video.value = el as HTMLVideoElement | null)"
            class="size-full object-cover"
            muted
            playsinline
            autoplay
          />
          <div class="pointer-events-none absolute inset-x-[10%] inset-y-[22%] rounded-lg border-2 border-white/80" aria-hidden="true" />
          <span
            v-if="continuous && progress"
            class="absolute top-3 left-3 rounded-full bg-black/65 px-3 py-1 text-sm font-semibold text-white tnum"
            aria-live="polite"
          >{{ progress }}</span>
          <NuxtButton
            v-if="scanner.canTorch.value"
            size="xl"
            color="neutral"
            square
            icon="i-lucide-flashlight"
            class="absolute right-3 bottom-3"
            :active="scanner.torchOn.value"
            active-color="primary"
            :aria-label="scanner.torchOn.value ? 'Desligar lanterna' : 'Ligar lanterna'"
            @click="scanner.toggleTorch()"
          />
        </div>
        <p v-if="scanner.error.value" role="alert" class="text-sm text-destructive">{{ scanner.error.value }}</p>
        <p v-else class="text-sm text-muted-foreground">{{ scanner.hint.value }}</p>
        <slot />
      </div>
    </template>
  </NuxtDrawer>
</template>
