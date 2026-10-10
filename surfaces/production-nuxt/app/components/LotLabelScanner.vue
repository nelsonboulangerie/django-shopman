<script setup lang="ts">
// "Ler etiqueta do lote" (v3 celular a, pino 3; plano §13 item 7): a câmera lê o QR
// da etiqueta de preparo e abre o Finalizar daquele lote. Sem câmera (ou sem
// permissão), o mesmo lugar aceita o código digitado.
import { useCodeScanner } from "~/composables/useCodeScanner";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{
  "update:open": [boolean];
  code: [string];
}>();

const typed = ref("");
const scanner = useCodeScanner((text) => emit("code", text));

watch(
  () => props.open,
  (now) => {
    if (now) {
      typed.value = "";
      void scanner.start();
    } else {
      scanner.stop();
    }
  },
);
onBeforeUnmount(() => scanner.stop());

function submitTyped() {
  const value = typed.value.trim();
  if (value) emit("code", value);
}
</script>

<template>
  <NuxtDrawer
    :open="open"
    title="Ler etiqueta do lote"
    direction="bottom"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <template #body>
      <div class="flex flex-col gap-3" data-lot-scanner>
        <div
          class="relative grid aspect-[4/3] w-full place-items-center overflow-hidden rounded-xl bg-black"
        >
          <video
            :ref="(el) => (scanner.video.value = el as HTMLVideoElement | null)"
            class="size-full object-cover"
            muted
            playsinline
            autoplay
          />
          <div
            class="pointer-events-none absolute inset-[18%] rounded-lg border-2 border-white/80"
            aria-hidden="true"
          />
          <!-- A lanterna é toque de câmera na mão: alvo grande, sobre o vídeo. -->
          <NuxtButton
            v-if="scanner.canTorch.value"
            size="xl"
            color="neutral"
            variant="solid"
            square
            icon="i-lucide-flashlight"
            class="absolute right-3 bottom-3 rounded-full"
            :aria-label="scanner.torchOn.value ? 'Desligar lanterna' : 'Ligar lanterna'"
            :aria-pressed="scanner.torchOn.value"
            @click="scanner.toggleTorch()"
          />
        </div>
        <p v-if="scanner.error.value" role="alert" class="op-label text-destructive">
          {{ scanner.error.value }}
        </p>
        <p v-else class="op-label text-muted-foreground">{{ scanner.hint.value }}</p>
        <form class="flex gap-2" @submit.prevent="submitTyped">
          <NuxtInput
            v-model="typed"
            class="flex-1"
            placeholder="Ou digite o código do lote"
            aria-label="Código do lote"
            autocomplete="off"
          />
          <NuxtButton
            type="submit"
            color="neutral"
            variant="outline"
            label="Abrir"
            :disabled="!typed.trim()"
          />
        </form>
      </div>
    </template>
  </NuxtDrawer>
</template>
