// A idade da posição do entregador (revisão das Entregas, F7b).
//
// O servidor manda a HORA da posição (`at`); a idade é conta da tela, que tem o relógio
// andando. Três faixas, uma frase cada, sem rótulo que peça para o leitor completar:
//  · até 20 s: "Posição agora". No mapa a moto não ganha etiqueta: estar ali é o agora.
//  · até 2 min: "Posição de há 40 s". No mapa: "Estava aqui há 40 s".
//  · depois: "Última posição há 3 min (12h45)". No mapa a moto ESMAECE e diz
//    "Estava aqui há 3 min". Sem amarelo: não há o que fazer, só saber.
import { clockHHMM } from "../../../operator-kit/app/presentation/courierProgress";

/** Até aqui a posição é "agora". */
export const FRESH_SECONDS = 20;
/** Daqui em diante a posição é velha: o marcador esmaece. */
export const STALE_SECONDS = 120;

export interface CourierPositionAge {
  seconds: number;
  fresh: boolean;
  stale: boolean;
  /** A frase do detalhe da corrida, sem quem disse. */
  sentence: string;
  /** A etiqueta junto da moto no mapa; vazia quando a posição é de agora. */
  mapLabel: string;
}

function ago(seconds: number): string {
  if (seconds < 60) return `${Math.max(FRESH_SECONDS, Math.floor(seconds / 10) * 10)} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h`;
}

/** A idade da posição tomada em `at` (ISO), vista em `now` (ms). Null sem hora legível. */
export function courierPositionAge(at: string | null | undefined, now: number): CourierPositionAge | null {
  const taken = at ? Date.parse(at) : Number.NaN;
  if (!Number.isFinite(taken)) return null;
  // Relógio do dispositivo atrasado em relação ao servidor: a posição é de agora.
  const seconds = Math.max(0, Math.floor((now - taken) / 1000));
  if (seconds < FRESH_SECONDS) {
    return { seconds, fresh: true, stale: false, sentence: "Posição agora", mapLabel: "" };
  }
  if (seconds < STALE_SECONDS) {
    return { seconds, fresh: false, stale: false, sentence: `Posição de há ${ago(seconds)}`, mapLabel: `Estava aqui há ${ago(seconds)}` };
  }
  return {
    seconds,
    fresh: false,
    stale: true,
    sentence: `Última posição há ${ago(seconds)} (${clockHHMM(taken)})`,
    mapLabel: `Estava aqui há ${ago(seconds)}`,
  };
}

/** "Posição agora, pela TaOn": a frase inteira do detalhe. */
export function courierPositionLine(
  position: { at: string; source_label: string } | null | undefined,
  now: number,
): string {
  const age = courierPositionAge(position?.at, now);
  if (!position || !age) return "";
  return position.source_label ? `${age.sentence}, ${position.source_label}` : age.sentence;
}
