// Janela de análise compartilhada entre as páginas (7/28/90 dias). O preset
// vira date_from/date_to na query; o backend normaliza e responde a janela
// efetiva — o contrato é do servidor, aqui é só UX.
export function useBiWindow() {
  const days = useState<number>("bi-window-days", () => 28);

  const range = computed(() => {
    const to = new Date();
    const from = new Date(to.getTime() - (days.value - 1) * 86_400_000);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return { date_from: iso(from), date_to: iso(to) };
  });

  return { days, range };
}
