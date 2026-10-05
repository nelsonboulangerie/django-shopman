<script setup lang="ts">
// A câmera do receber em folha de baixo: "Ler EAN", "Bipar cada volume" e "Ler da
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
  <UiSheet :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <UiSheetContent side="bottom" composition="bare" class="max-h-[92dvh]" :data-code-scanner="title">
      <UiSheetHeader class="border-b border-border p-4">
        <div class="flex items-start justify-between gap-2">
          <UiSheetTitle class="text-base">{{ title }}</UiSheetTitle>
          <UiSheetX placement="inline" />
        </div>
        <UiSheetDescription>{{ hint }}</UiSheetDescription>
      </UiSheetHeader>
      <div class="flex flex-col gap-3 overflow-y-auto p-4">
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
            class="absolute top-3 left-3 rounded-full bg-black/65 px-3 py-1 op-label font-semibold text-white tnum"
            aria-live="polite"
          >{{ progress }}</span>
          <button
            v-if="scanner.canTorch.value"
            type="button"
            class="absolute right-3 bottom-3 grid size-12 place-items-center rounded-full bg-black/60 text-white"
            :aria-label="scanner.torchOn.value ? 'Desligar lanterna' : 'Ligar lanterna'"
            @click="scanner.toggleTorch()"
          >
            <Icon name="lucide:flashlight" class="size-5" />
          </button>
        </div>
        <p v-if="scanner.error.value" role="alert" class="op-label text-destructive">{{ scanner.error.value }}</p>
        <p v-else class="op-label font-normal text-muted-foreground">{{ scanner.hint.value }}</p>
        <slot />
      </div>
    </UiSheetContent>
  </UiSheet>
</template>
