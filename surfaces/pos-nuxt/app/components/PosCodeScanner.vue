<script setup lang="ts">
// "Ler código" pela câmera (v4 tablet a, v3 celular 6): o tablet e o celular não
// têm leitor HID, e a mercearia (geleia, chá em lata) tem código de barras; a
// encomenda tem o QR da mensagem que o cliente recebeu. Tela cheia, lanterna,
// fechar e "Digite o código" quando a câmera não lê. Ao ler, o dispositivo vibra
// e o código sai por `code`: quem abriu decide o que ele é (produto, encomenda).
//
// Mesmo leitor do Compras (`@zxing`, carregado só quando a câmera abre), com os
// formatos de varejo e o QR.
const props = defineProps<{
  open: boolean;
  title: string;
}>();
const emit = defineEmits<{
  "update:open": [boolean];
  code: [string];
  type: [];
}>();

const video = ref<HTMLVideoElement | null>(null);
const error = ref("");
const hint = ref("");
const canTorch = ref(false);
const torchOn = ref(false);
let controls: { stop: () => void; switchTorch?: (onOff: boolean) => Promise<void> } | null = null;
let accepted = false;

function stop() {
  controls?.stop();
  controls = null;
  const source = video.value?.srcObject;
  if (source && typeof (source as MediaStream).getTracks === "function") {
    (source as MediaStream).getTracks().forEach((track) => track.stop());
  }
  if (video.value) video.value.srcObject = null;
  canTorch.value = false;
  torchOn.value = false;
}

async function createReader() {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
    import("@zxing/browser"),
    import("@zxing/library"),
  ]);
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [
    BarcodeFormat.QR_CODE,
    BarcodeFormat.EAN_13,
    BarcodeFormat.EAN_8,
    BarcodeFormat.UPC_A,
    BarcodeFormat.UPC_E,
    BarcodeFormat.CODE_128,
    BarcodeFormat.CODE_39,
  ]);
  hints.set(DecodeHintType.TRY_HARDER, true);
  return new BrowserMultiFormatReader(hints, {
    delayBetweenScanAttempts: 200,
    delayBetweenScanSuccess: 900,
    tryPlayVideoTimeout: 4500,
  });
}

function accept(raw: string) {
  const value = raw.trim();
  if (!value || accepted) return;
  accepted = true;
  try {
    navigator.vibrate?.(60);
  } catch {
    // silêncio-deliberado: vibrar é enfeite; sem ele, o código sai do mesmo jeito.
  }
  stop();
  emit("code", value);
  emit("update:open", false);
}

async function start() {
  error.value = "";
  accepted = false;
  hint.value = "Abrindo câmera...";
  if (!import.meta.client || !navigator.mediaDevices?.getUserMedia) {
    error.value = "Câmera indisponível neste navegador. Digite o código.";
    return;
  }
  await nextTick();
  try {
    if (!video.value) throw new Error("scanner_video_missing");
    const reader = await createReader();
    hint.value = "Centralize o QR ou alinhe todo o código de barras dentro do quadro.";
    controls = await reader.decodeFromConstraints(
      { audio: false, video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } } },
      video.value,
      (result, _error, current) => {
        controls = current;
        canTorch.value = Boolean(current.switchTorch);
        const text = result?.getText();
        if (text) accept(text);
      },
    );
  } catch {
    error.value = "Não consegui abrir a câmera. Confira a permissão do navegador ou digite o código.";
    stop();
  }
}

async function toggleTorch() {
  if (!controls?.switchTorch) return;
  const next = !torchOn.value;
  try {
    await controls.switchTorch(next);
    torchOn.value = next;
  } catch {
    // silêncio-deliberado: lanterna é enfeite; o botão some e a leitura segue.
    canTorch.value = false;
  }
}

function close() {
  stop();
  emit("update:open", false);
}
function typeInstead() {
  close();
  emit("type");
}

watch(() => props.open, (open) => {
  if (open) void start();
  else stop();
}, { immediate: true });
onBeforeUnmount(stop);
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => { if (!value) close(); }">
    <UiDialogContent
      v-if="open"
      fullscreen
      hide-close
      class="flex flex-col bg-black text-white"
      :aria-label="title"
      data-pos-code-scanner
    >
      <div class="flex h-16 shrink-0 items-center gap-3 px-3">
        <NuxtButton color="neutral" variant="ghost" class="grid size-12 place-items-center rounded-full bg-white/15 justify-center text-white hover:bg-white/25" aria-label="Fechar leitor" @click="close">
          <Icon name="lucide:x" class="size-6" />
        </NuxtButton>
        <p class="min-w-0 flex-1 truncate text-center text-base font-semibold">{{ title }}</p>
        <NuxtButton
          color="neutral"
          variant="ghost"
          class="grid size-12 place-items-center rounded-full disabled:opacity-30 justify-center text-white hover:bg-white/25"
          :class="torchOn ? 'bg-white text-black' : 'bg-white/15'"
          :disabled="!canTorch"
          :aria-pressed="torchOn"
          aria-label="Lanterna"
          @click="toggleTorch"
        >
          <Icon name="lucide:flashlight" class="size-6" />
        </NuxtButton>
      </div>
      <div class="relative min-h-0 flex-1 overflow-hidden">
        <video ref="video" muted playsinline class="size-full object-cover" />
        <div class="pointer-events-none absolute inset-0 grid place-items-center" aria-hidden="true">
          <div class="aspect-square w-[min(70vw,22rem)] rounded-3xl border-4 border-success/80" />
        </div>
      </div>
      <div class="grid shrink-0 gap-3 p-4 text-center">
        <p class="text-sm text-white/80" role="status">{{ error || hint }}</p>
        <NuxtButton color="neutral" variant="ghost" class="mx-auto inline-flex h-12 items-center gap-2 rounded-full bg-white/15 px-5 text-base font-semibold text-white hover:bg-white/25" @click="typeInstead">
          <Icon name="lucide:keyboard" class="size-5" />
          Digite o código
        </NuxtButton>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
