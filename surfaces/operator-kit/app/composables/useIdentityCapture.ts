// Captura de identificação (PIN + crachá) — UM caminho só, no DOCUMENTO.
//
// A tela de identificação recebe entrada por três portas: o leitor USB de crachá
// (um teclado que "digita" o token depressa e termina com Enter), o teclado
// físico do balcão, e os botões do pad na tela. As três alimentam o MESMO buffer,
// imediatamente — nenhuma tecla é descartada na chegada, então quem digita
// depressa nunca perde dígito. A pergunta "crachá ou gente?" fica para o Enter,
// quando a passada terminou e a cadência interna conta a verdade (a regra é pura
// e mora em `presentation/operatorLock`: `resolveEnter`).
//
// A captura mora no documento, em fase de CAPTURE, e o foco fica onde o operador
// deixou — um campo escondido com `autofocus` funciona exatamente uma vez: no
// primeiro toque do operador o foco vai embora e o crachá para de ser lido, sem
// nada na tela dizendo isso. Três consequências que valem o cuidado:
//
//   - Tecla que a captura aceita ([0-9a-f], fora de campo de texto) é CONSUMIDA
//     (`stopPropagation`): a tela de identificação é modal, e nem o token do
//     crachá nem o PIN podem vazar aos listeners da tela por baixo (numpad do
//     carrinho, atalhos globais). Nenhuma tecla vaza — nem a primeira.
//   - O Enter do leitor é consumido (`preventDefault`) só quando a passada é
//     mesmo um crachá. Sem isso, o Enter final ativaria o botão que estivesse
//     com o foco — o leitor identificaria o operador E clicaria em algo por
//     conta própria. Enter de gente segue o caminho normal (submete o PIN
//     quando dá, e mais nada).
//   - Campo de texto de verdade (nome livre) é do dono: as teclas continuam
//     chegando ao campo; a captura só OBSERVA (o leitor segue funcionando até
//     com um input focado), sem pôr esses dígitos no PIN.
//
// O token é credencial: fica só neste buffer em memória, some no Enter, e NUNCA
// é logado nem exibido (o mesmo tratamento que o PIN recebe).

// Lifecycle importado do `vue` explicitamente (como em `useConnectivity`): o
// composable roda igual no env `nuxt` e no harness `node` dos apps que fazem extends.
import { computed, onBeforeUnmount, onMounted, shallowRef } from "vue";

import {
  type CapturedKey,
  backspaceCapture,
  captureKey,
  capturedPin,
  isCaptureKey,
  resolveEnter,
} from "../presentation/operatorLock";

export interface IdentityCaptureOptions {
  /** O pad de PIN está visível? Dígito só vira bolinha (e Backspace/Enter só
   *  são consumidos) com o pad na tela. */
  padVisible: () => boolean;
  /** Enquanto devolver false, o Enter nunca resolve crachá (ex.: verificação em
   *  curso — autorizar duas vezes pelo mesmo gesto — ou o leitor desligado pelo
   *  chamador). A DIGITAÇÃO continua entrando no buffer: bloquear a submissão
   *  nunca pode custar dígito. */
  badgeEnabled?: () => boolean;
  /** O Enter humano pode submeter agora? (PIN completo e nada em curso.) */
  canSubmitEnter: () => boolean;
  /** Passada de crachá fechada no Enter. O retorno é ignorado de propósito
   *  (`unknown`): quem passa `unlock` devolve Promise<boolean>, e a captura não
   *  tem o que fazer com esse booleano — o erro já vira toast no composable do
   *  lock. */
  onBadge: (token: string) => unknown;
  /** Enter humano com PIN pronto. */
  onSubmit: () => void;
  /** Dígito digitado ANTES de haver pad na tela — a lista de gente ainda está
   *  aberta, e ali "2" quer dizer "sou o segundo da lista". Opcional: só quem
   *  mostra lista numerada passa.
   *
   *  Só dispara depois de `PICK_QUIET_MS` de SILÊNCIO, e é esse silêncio que
   *  separa o dedo do leitor. O token do crachá é hexadecimal, então mais da
   *  metade dos crachás começa com um dígito — sem a espera, uma passada
   *  escolheria uma pessoa na primeira tecla e o resto do token viraria PIN
   *  (com a leitura por crachá desligada, esse PIN chegava a ser SUBMETIDO).
   *  A primeira tecla de uma rajada não se distingue olhando para trás: não há
   *  nada antes dela. Olhando para a frente, sim — o leitor entrega a segunda
   *  em ~10-30ms, e quem escolheu alguém na tela leva muito mais que isso para
   *  ir ao pad. Qualquer tecla dentro da janela cancela, e cancelar não faz
   *  nada: o atalho simplesmente não age, e a tela fica como estava. */
  onDigitPick?: (digit: string) => void;
}

/** Silêncio que prova que o dígito veio de um dedo, não de um leitor. Folgado
 *  dos dois lados: rajada de HID nunca chega perto (10-30ms entre teclas), e
 *  ninguém escolhe um nome e começa a digitar o PIN em menos de um décimo de
 *  segundo — entre as duas coisas há uma decisão. */
export const PICK_QUIET_MS = 120;

export function useIdentityCapture(options: IdentityCaptureOptions) {
  const badgeEnabled = options.badgeEnabled ?? (() => true);

  const keys = shallowRef<readonly CapturedKey[]>([]);
  let lastAt = 0;
  let pickTimer: ReturnType<typeof setTimeout> | null = null;

  /** Desarma a escolha por número em curso. Chamado por QUALQUER outra entrada:
   *  se veio mais alguma coisa, aquilo era uma rajada, não um dedo. */
  function cancelPick(): void {
    if (pickTimer === null) return;
    clearTimeout(pickTimer);
    pickTimer = null;
  }

  /** O PIN visível, derivado do buffer — a tela reflete cada entrada na hora. */
  const pin = computed(() => capturedPin(keys.value));

  function feed(char: string, pinEligible: boolean): void {
    const now = Date.now();
    keys.value = captureKey(keys.value, char, lastAt ? now - lastAt : 0, pinEligible);
    lastAt = now;
  }

  /** Botão do pad na tela: entra no MESMO buffer, com o relógio de verdade —
   *  clique é dedo por definição, e a cadência registrada diz isso sozinha. */
  function pressDigit(digit: string): void {
    feed(digit, true);
  }

  function backspace(): void {
    keys.value = backspaceCapture(keys.value);
  }

  function clear(): void {
    cancelPick();
    keys.value = [];
    lastAt = 0;
  }

  function isEditingTarget(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    return (
      !!el
      && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)
    );
  }

  function onKeydown(event: KeyboardEvent): void {
    // Atalho com modificador é comando do sistema, não identificação.
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const editing = isEditingTarget(event.target);
    // Backspace e Enter também quebram o silêncio: o que vinha antes deles não
    // era um dedo escolhendo um nome.
    if (event.key === "Backspace" || event.key === "Enter") cancelPick();

    if (isCaptureKey(event.key)) {
      const toPin = options.padVisible() && !editing;
      feed(event.key, toPin);
      // Sem pad na tela o dígito PODE ser escolha de pessoa — ou a primeira
      // tecla de um crachá. Quem decide é o silêncio depois dele. O buffer já
      // recebeu a tecla acima e continua intocado nos dois casos: se for
      // crachá, o token fecha normalmente no Enter.
      cancelPick();
      if (!toPin && !editing && options.onDigitPick && /^[0-9]$/.test(event.key)) {
        const digit = event.key;
        pickTimer = setTimeout(() => {
          pickTimer = null;
          options.onDigitPick?.(digit);
        }, PICK_QUIET_MS);
      }
      if (!editing) {
        // Consumida: a tela de identificação é modal, nada vaza para baixo.
        event.stopPropagation();
        // Dígito que virou bolinha não deve ter outro efeito default.
        if (toPin) event.preventDefault();
      }
      return;
    }

    if (event.key === "Backspace") {
      if (editing || !options.padVisible()) return;
      event.preventDefault();
      event.stopPropagation();
      backspace();
      return;
    }

    if (event.key !== "Enter") return;

    if (badgeEnabled()) {
      const gapMs = lastAt ? Date.now() - lastAt : Number.POSITIVE_INFINITY;
      const resolved = resolveEnter(keys.value, gapMs);
      if (resolved.kind === "badge") {
        // Consome o Enter do leitor para ele não ativar o botão focado.
        event.preventDefault();
        event.stopPropagation();
        keys.value = resolved.keys;
        lastAt = 0;
        options.onBadge(resolved.token);
        return;
      }
    }
    // Enter de gente: submete o PIN quando dá; senão segue o caminho normal
    // (num campo de texto ele pertence ao formulário, num botão focado clica).
    if (editing || !options.padVisible() || !options.canSubmitEnter()) return;
    event.preventDefault();
    event.stopPropagation();
    options.onSubmit();
  }

  onMounted(() => document.addEventListener("keydown", onKeydown, true));
  onBeforeUnmount(() => {
    document.removeEventListener("keydown", onKeydown, true);
    clear();
  });

  return { pin, pressDigit, backspace, clear };
}
