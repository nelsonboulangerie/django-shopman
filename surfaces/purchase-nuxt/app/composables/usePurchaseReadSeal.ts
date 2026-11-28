// O ponto de conexão no selo da linha do chão (`OperatorCompactBar`), no celular. É a
// mesma leitura do `PurchaseReadStatus` da mesa, dita sem fingir ao vivo: o Compras não
// tem SSE, lê ao abrir e em Atualizar. Leitura em dia é `calm` (atualiza quando pedem);
// sem leitura é `off`.
export function usePurchaseReadSeal() {
  const { pending, readonlyFallback } = usePurchaseDesk();
  const readAt = useState("purchase-read-at", () => "");
  const tone = computed(() => (readonlyFallback.value ? ("off" as const) : ("calm" as const)));
  const connLabel = computed(() => (pending.value ? "Lendo a base de compras" : "Lê ao abrir e em Atualizar"));
  return { tone, time: readAt, connLabel };
}
