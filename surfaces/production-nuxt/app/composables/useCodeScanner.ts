// Leitor pela câmera (QR e código de barras), o mesmo motor do Compras
// (`@zxing/browser`, carregado só quando a câmera abre). O navegador do celular
// e do tablet dá a câmera traseira com `getUserMedia`; sem câmera (desktop sem
// webcam, permissão negada), o leitor diz isso e a tela oferece digitar o código.
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

async function createReader() {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] =
    await Promise.all([import("@zxing/browser"), import("@zxing/library")]);
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [
    BarcodeFormat.QR_CODE,
    BarcodeFormat.CODE_128,
    BarcodeFormat.EAN_13,
    BarcodeFormat.DATA_MATRIX,
  ]);
  hints.set(DecodeHintType.TRY_HARDER, true);
  return new BrowserMultiFormatReader(hints, {
    delayBetweenScanAttempts: 250,
    delayBetweenScanSuccess: 900,
    tryPlayVideoTimeout: 4500,
  });
}

export function useCodeScanner(onCode: (text: string) => void): CodeScanner {
  const open = ref(false);
  const error = ref("");
  const hint = ref("");
  const canTorch = ref(false);
  const torchOn = ref(false);
  const video = ref<HTMLVideoElement | null>(null);
  const controls = shallowRef<ScannerControls | null>(null);
  let accepted = false;

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

  async function start() {
    if (open.value) return;
    error.value = "";
    accepted = false;
    if (!import.meta.client || !navigator.mediaDevices?.getUserMedia) {
      error.value =
        "Câmera indisponível neste navegador. Digite o código impresso na etiqueta.";
      return;
    }
    open.value = true;
    hint.value = "Abrindo câmera…";
    await nextTick();
    try {
      if (!video.value) throw new Error("scanner_video_missing");
      const reader = await createReader();
      hint.value = "Centralize o código da etiqueta no quadro.";
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
          if (!text || accepted) return;
          accepted = true;
          stop();
          onCode(text);
        },
      )) as ScannerControls;
    } catch {
      error.value =
        "Não consegui abrir a câmera. Libere a câmera para este app ou digite o código.";
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
