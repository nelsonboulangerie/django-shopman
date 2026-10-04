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
  <UiSheet :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <UiSheetContent side="bottom" title="Ler etiqueta do lote">
      <template #content>
        <div class="flex flex-col gap-3 px-4 pb-6" data-lot-scanner>
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
          <p v-if="scanner.error.value" role="alert" class="op-label text-destructive">
            {{ scanner.error.value }}
          </p>
          <p v-else class="op-label text-muted-foreground">{{ scanner.hint.value }}</p>
          <form class="flex gap-2" @submit.prevent="submitTyped">
            <UiInput
              v-model="typed"
              class="h-12 flex-1"
              placeholder="Ou digite o código do lote"
              aria-label="Código do lote"
              autocomplete="off"
            />
            <UiButton type="submit" variant="outline" class="h-12" :disabled="!typed.trim()">
              Abrir
            </UiButton>
          </form>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>
</template>
