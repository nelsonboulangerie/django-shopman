// Leitor pela câmera do receber: "Ler EAN" (código da caixa), "Bipar cada volume"
// (uma leitura por volume, em sequência) e "Ler da embalagem" (GS1: validade e
// lote). O mesmo motor da leitura da NF (`@zxing/browser`, carregado só quando a
// câmera abre). Sem câmera ou sem permissão, o leitor diz isso e a tela segue
// com o gesto manual (digitar, o stepper, a escolha de dia).
import { ref, shallowRef, type Ref } from "vue";

type ScannerControls = {
  stop: () => void;
  switchTorch?: (on: boolean) => Promise<void>;
};

export interface CodeScanner {
  open: Ref<boolean>;
  error: Ref<string>;
  hint: Ref<string>;
  canTorch: Ref<boolean>;
  torchOn: Ref<boolean>;
  video: Ref<HTMLVideoElement | null>;
  start: () => Promise<void>;
  stop: () => void;
  toggleTorch: () => Promise<void>;
}

export interface CodeScannerOptions {
  /** Continua lendo depois da primeira leitura ("Bipar cada volume"). */
  continuous?: boolean;
  /** O mesmo código lido de novo antes deste intervalo não conta (ms). */
  repeatAfterMs?: number;
}

async function createReader() {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] =
    await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [
    BarcodeFormat.EAN_13,
    BarcodeFormat.EAN_8,
    BarcodeFormat.UPC_A,
    BarcodeFormat.ITF,
    BarcodeFormat.CODE_128,
    BarcodeFormat.DATA_MATRIX,
    BarcodeFormat.QR_CODE,
  ]);
  hints.set(DecodeHintType.TRY_HARDER, true);
  return new BrowserMultiFormatReader(hints, {
    delayBetweenScanAttempts: 200,
    delayBetweenScanSuccess: 700,
    tryPlayVideoTimeout: 4500,
  });
}

export function useCodeScanner(
  onCode: (text: string) => void,
  options: CodeScannerOptions = {},
): CodeScanner {
  const open = ref(false);
  const error = ref("");
  const hint = ref("");
  const canTorch = ref(false);
  const torchOn = ref(false);
  const video = ref<HTMLVideoElement | null>(null);
  const controls = shallowRef<ScannerControls | null>(null);
  let accepted = false;
  const lastSeen = new Map<string, number>();

  function stop() {
    controls.value?.stop();
    controls.value = null;
    const source = video.value?.srcObject as MediaStream | null | undefined;
    source?.getTracks?.().forEach((track) => track.stop());
    if (video.value) video.value.srcObject = null;
    canTorch.value = false;
    torchOn.value = false;
    open.value = false;
  }

  function accept(text: string) {
    if (options.continuous) {
      const now = Date.now();
      const seen = lastSeen.get(text) ?? 0;
      if (now - seen < (options.repeatAfterMs ?? 1500)) return;
      lastSeen.set(text, now);
      if (typeof navigator !== "undefined") navigator.vibrate?.(40);
      onCode(text);
      return;
    }
    if (accepted) return;
    accepted = true;
    if (typeof navigator !== "undefined") navigator.vibrate?.(40);
    stop();
    onCode(text);
  }

  async function start() {
    if (open.value) return;
    error.value = "";
    accepted = false;
    lastSeen.clear();
    if (!import.meta.client || !navigator.mediaDevices?.getUserMedia) {
      error.value = "Câmera indisponível neste navegador. Siga pelo gesto manual.";
      return;
    }
    open.value = true;
    hint.value = "Abrindo câmera…";
    await nextTick();
    try {
      if (!video.value) throw new Error("scanner_video_missing");
      const reader = await createReader();
      hint.value = "Centralize o código no quadro.";
      controls.value = (await reader.decodeFromConstraints(
        {
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        },
        video.value,
        (result, _error, current) => {
          controls.value = current as ScannerControls;
          canTorch.value = Boolean((current as ScannerControls).switchTorch);
          const text = result?.getText()?.trim();
          if (text) accept(text);
        },
      )) as ScannerControls;
    } catch {
      error.value = "Não consegui abrir a câmera. Libere a câmera para este app ou siga pelo gesto manual.";
      stop();
    }
  }

  async function toggleTorch() {
    if (!controls.value?.switchTorch) return;
    try {
      await controls.value.switchTorch(!torchOn.value);
      torchOn.value = !torchOn.value;
    } catch {
      canTorch.value = false;
    }
  }

  return { open, error, hint, canTorch, torchOn, video, start, stop, toggleTorch };
}
