// Leitor de código de barras pela câmera — primitiva do operator-kit, ZERO
// dependência. Usa a BarcodeDetector nativa (Chrome/Android); onde ela não
// existe, diz que a câmera não lê e a tela segue pelo gesto manual. O Compras
// mantém o leitor @zxing (funciona em iOS/Safari); quando a primitiva nativa
// cobrir o parque, aquele leitor migra para cá.
import { nextTick, ref, shallowRef, type Ref } from "vue";

export interface BarcodeScanner {
  open: Ref<boolean>;
  error: Ref<string>;
  hint: Ref<string>;
  supported: Ref<boolean>;
  video: Ref<HTMLVideoElement | null>;
  start: () => Promise<void>;
  stop: () => void;
}

type DetectedCode = { rawValue: string };
type DetectorLike = {
  detect: (source: CanvasImageSource) => Promise<DetectedCode[]>;
};
type DetectorCtor = new (options?: { formats?: string[] }) => DetectorLike;

// EAN/UPC primeiro: é o que identifica o item. QR e Data Matrix entram porque o
// mesmo código pode vir em 2D (GS1).
const FORMATS = [
  "ean_13",
  "ean_8",
  "upc_a",
  "upc_e",
  "code_128",
  "itf",
  "qr_code",
  "data_matrix",
];

function detectorCtor(): DetectorCtor | null {
  const candidate = (globalThis as { BarcodeDetector?: DetectorCtor })
    .BarcodeDetector;
  return typeof candidate === "function" ? candidate : null;
}

export function useBarcodeScanner(
  onCode: (text: string) => void,
): BarcodeScanner {
  const open = ref(false);
  const error = ref("");
  const hint = ref("");
  const supported = ref(false);
  const video = ref<HTMLVideoElement | null>(null);
  const stream = shallowRef<MediaStream | null>(null);
  let frame = 0;
  let accepted = false;

  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    stream.value?.getTracks().forEach((track) => track.stop());
    stream.value = null;
    if (video.value) video.value.srcObject = null;
    open.value = false;
  }

  async function loop(detector: DetectorLike) {
    if (!open.value || accepted) return;
    try {
      const codes = await detector.detect(video.value as HTMLVideoElement);
      const text = codes?.[0]?.rawValue?.trim();
      if (text) {
        accepted = true;
        if (typeof navigator !== "undefined") navigator.vibrate?.(40);
        stop();
        onCode(text);
        return;
      }
    } catch {
      // Quadro sem código: o detector reclama e a gente tenta o próximo.
    }
    frame = requestAnimationFrame(() => void loop(detector));
  }

  async function start() {
    if (open.value) return;
    error.value = "";
    accepted = false;
    const Ctor = detectorCtor();
    if (!import.meta.client || !Ctor || !navigator.mediaDevices?.getUserMedia) {
      supported.value = false;
      error.value =
        "A câmera deste dispositivo não lê código de barras. Digite o código.";
      return;
    }
    supported.value = true;
    open.value = true;
    hint.value = "Abrindo câmera…";
    await nextTick();
    try {
      stream.value = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });
      if (!video.value) throw new Error("scanner_video_missing");
      video.value.srcObject = stream.value;
      await video.value.play();
      hint.value = "Centralize o código no quadro.";
      const detector = new Ctor({ formats: FORMATS });
      frame = requestAnimationFrame(() => void loop(detector));
    } catch {
      error.value =
        "Não consegui abrir a câmera. Libere a câmera para este app ou digite o código.";
      stop();
    }
  }

  return { open, error, hint, supported, video, start, stop };
}
