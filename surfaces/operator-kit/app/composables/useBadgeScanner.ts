// Leitor de crachá (HID) — captura no DOCUMENTO, não num campo focado.
//
// Um leitor USB de crachá é um teclado: ele "digita" o token depressa e termina com
// Enter. A tentação é pôr um campo escondido com `autofocus` e ler o `v-model` — e
// funciona exatamente uma vez. No primeiro toque do operador (escolher o nome, tocar
// no pad, qualquer botão) o foco vai embora do campo e o crachá para de ser lido, sem
// nada na tela dizendo isso. Num kiosk de balcão, "recarregue a página" não é resposta.
//
// Então a captura mora no documento, em fase de CAPTURE, e o foco fica onde o operador
// deixou. Duas consequências que valem o cuidado:
//
//   - A JANELA DE TEMPO separa leitor de dedo. Teclas separadas por mais de
//     `BADGE_MAX_GAP_MS` recomeçam o buffer, então teclas soltas ao longo do turno não
//     se somam num token falso. A regra é pura (`pushBadgeKey`) e testada sem relógio.
//   - O Enter do leitor é CONSUMIDO (`preventDefault`) só quando o buffer é mesmo um
//     crachá. Sem isso, o Enter final ativaria o botão que estivesse com o foco — o
//     leitor identificaria o operador E clicaria em algo por conta própria. Quando não
//     é crachá, o Enter segue seu caminho normal (teclado de gente continua inteiro).
//
// O token é credencial: fica só neste buffer em memória, some no Enter, e NUNCA é
// logado nem exibido (o mesmo tratamento que o PIN recebe).

// Lifecycle importado do `vue` explicitamente (como em `useConnectivity`): o composable
// roda igual no env `nuxt` e no harness `node` dos apps que fazem extends.
import { onBeforeUnmount, onMounted } from "vue";

import { BADGE_MAX_GAP_MS, isLikelyBadge, pushBadgeKey } from "../presentation/operatorLock";

export interface BadgeScannerOptions {
  /** Enquanto devolver false, o leitor é ignorado (ex.: a tela está trocando o PIN,
   *  onde há campos de texto de verdade e o Enter pertence ao formulário). */
  enabled?: () => boolean;
  /** Janela entre teclas da MESMA passada. Padrão `BADGE_MAX_GAP_MS`. */
  maxGapMs?: number;
}

export function useBadgeScanner(
  // O retorno é ignorado de propósito (`unknown`): quem passa `unlock` devolve
  // Promise<boolean>, e o leitor não tem o que fazer com esse booleano — o erro
  // já vira toast no composable do lock.
  onScan: (token: string) => unknown,
  options: BadgeScannerOptions = {},
) {
  const isEnabled = options.enabled ?? (() => true);
  const maxGapMs = options.maxGapMs ?? BADGE_MAX_GAP_MS;

  let buffer = "";
  let lastAt = 0;

  function reset(): void {
    buffer = "";
    lastAt = 0;
  }

  function onKeydown(event: KeyboardEvent): void {
    if (!isEnabled()) {
      reset();
      return;
    }
    // Atalho com modificador é comando do sistema, não crachá.
    if (event.ctrlKey || event.metaKey || event.altKey) {
      reset();
      return;
    }

    const now = Date.now();
    const gapMs = lastAt ? now - lastAt : 0;

    if (event.key === "Enter") {
      const token = buffer.trim();
      reset();
      // Enter que chega tarde não fecha uma passada: é gente apertando Enter.
      if (gapMs > maxGapMs || !isLikelyBadge(token)) return;
      // Consome o Enter do leitor para ele não ativar o botão focado.
      event.preventDefault();
      event.stopPropagation();
      onScan(token);
      return;
    }

    buffer = pushBadgeKey(buffer, event.key, gapMs, maxGapMs);
    lastAt = now;
  }

  onMounted(() => document.addEventListener("keydown", onKeydown, true));
  onBeforeUnmount(() => {
    document.removeEventListener("keydown", onKeydown, true);
    reset();
  });

  return { reset };
}
