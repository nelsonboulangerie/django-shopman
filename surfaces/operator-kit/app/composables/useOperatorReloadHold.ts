/**
 * Razões NOMEADAS pelas quais esta superfície não pode ser recarregada agora.
 *
 * Quem sabe que há venda no meio é a tela, não o kit. Em vez de o kit adivinhar
 * (ou de cada app copiar a mesma trava), a tela declara a razão pelo nome e o
 * `usePwaAutoUpdate` só aplica a versão nova quando nenhuma está de pé. O nome
 * viaja para o log: "não aplicou porque `tab_open`" é diagnosticável; "não aplicou"
 * não é.
 *
 * Gêmeo do `pos-payment-hold` do auto-lock, e de propósito SEPARADO dele: adiar o
 * cadeado é uma pergunta mais estreita (pagamento em curso) do que adiar um reload
 * (qualquer rascunho na tela).
 */
export function useOperatorReloadHold() {
  const holds = useState<Record<string, boolean>>("operator-reload-hold", () => ({}));

  /** Liga/desliga uma razão. Idempotente: pode ser chamada de um `watchEffect`. */
  function hold(reason: string, active: boolean) {
    const current = holds.value[reason] === true;
    if (current === active) return;
    if (active) holds.value = { ...holds.value, [reason]: true };
    else {
      const next = { ...holds.value };
      delete next[reason];
      holds.value = next;
    }
  }

  /** Ordenadas para o log não mudar de razão a cada render. */
  const reasons = computed(() => Object.keys(holds.value).filter((key) => holds.value[key]).sort());

  return { reasons, hold };
}
