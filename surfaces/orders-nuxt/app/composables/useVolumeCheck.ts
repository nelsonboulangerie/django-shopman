// A conferência das sacolas no despacho, na tela: o leitor do posto Saída bipa
// o QR da Via Pedido e a faixa diz "Conferindo o pedido U68: 2 de 3 sacolas".
// Sacola de outro pedido é aviso forte, com som grave; nada segura a saída.
// A regra da faixa é pura (`presentation/volumeCheck`); o leitor é o do kit.
import { useCodeScanner } from "../../../operator-kit/app/composables/useCodeScanner";
import {
  EMPTY_CONFERENCE,
  VOLUME_CODE,
  applyResult,
  expectedRef,
  type ConferenceState,
  type VolumeCheckResponse,
} from "~/presentation/volumeCheck";

/** Sacola conferida: duas notas curtas, subindo. */
const CHECKED_NOTES = [
  { f: 660, t: 0, d: 0.12 },
  { f: 880, t: 0.12, d: 0.16 },
];
/** Sacola errada: grave e longa, três vezes (tem de cortar o barulho do balcão). */
const WRONG_NOTES = [
  { f: 220, t: 0, d: 0.35 },
  { f: 220, t: 0.45, d: 0.35 },
  { f: 220, t: 0.9, d: 0.5 },
];

export function useVolumeCheck(options: {
  /** O pedido fixo da tela (o detalhe aberto); vazio no quadro. */
  fixedRef?: () => string;
  /** Só escuta com a tela destravada. */
  enabled: () => boolean;
  /** Releia a tela depois de uma bipada que contou. */
  onChecked?: () => void;
}) {
  const state = ref<ConferenceState>({ ...EMPTY_CONFERENCE });
  const busy = new Set<string>();
  const { beep: beepChecked } = useAlertSound("gestor_volume_sound", { notes: CHECKED_NOTES });
  const { beep: beepWrong } = useAlertSound("gestor_volume_sound", { notes: WRONG_NOTES });

  async function check(code: string, expected = expectedRef(state.value, options.fixedRef?.() ?? "")) {
    if (busy.has(code)) return;
    busy.add(code);
    try {
      const result = await $fetch<VolumeCheckResponse>("/api/v1/backstage/orders/volume-check/", {
        method: "POST",
        body: { code, expected_ref: expected },
      });
      state.value = applyResult(state.value, result);
      if (result.outcome === "checked") {
        beepChecked();
        options.onChecked?.();
      } else if (result.outcome === "other_order") {
        beepWrong();
      }
    } catch (error) {
      state.value = {
        ...state.value,
        alarm: { tone: "warning", message: httpErrorMessage(error, "Não deu para conferir esta sacola. Bipe de novo.") },
      };
    } finally {
      busy.delete(code);
    }
  }

  useCodeScanner({
    format: VOLUME_CODE,
    enabled: options.enabled,
    onCode: (code) => check(code),
    onInvalid: () => {
      state.value = {
        ...state.value,
        alarm: { tone: "warning", message: "Código não reconhecido: não é de uma Via Pedido desta loja." },
      };
    },
  });

  /** "Conferir este": a sacola errada vira o pedido em conferência. */
  function switchTo(ref: string) {
    state.value = { conference: { ref, checked: 0, total: 0 }, alarm: null };
  }

  function dismissAlarm() {
    state.value = { ...state.value, alarm: null };
  }

  function end() {
    state.value = { ...EMPTY_CONFERENCE };
  }

  return { state, check, switchTo, dismissAlarm, end };
}
