// "Compartilhar esta leitura" como item do ⋯ do cabeçalho (`OperatorReadingPageMenu`),
// e não como botão próprio na barra do celular: na barra de 390 px o botão a mais
// disputava espaço com o título da tela. O item só existe onde há a folha do
// sistema (Web Share); sem ela, o "Copiar link desta leitura" do mesmo menu já faz o
// gesto. A leitura inteira (período, recortes) mora na URL: o link É a leitura.
/** O item do ⋯ (forma do `DropdownMenuItem` do Nuxt UI, que o app não importa direto). */
interface ShareMenuItem {
  label: string;
  icon: string;
  onSelect: () => void;
}

export function useBiShareMenuItems() {
  const canShare = ref(false);
  onMounted(() => {
    canShare.value = typeof navigator.share === "function";
  });

  async function shareReading() {
    try {
      await navigator.share({ title: document.title, url: window.location.href });
    } catch (error) {
      if ((error as DOMException)?.name === "AbortError") return;
      useSonner.warning("Não deu para compartilhar. Use \"Copiar link desta leitura\", no mesmo menu.");
    }
  }

  return computed<ShareMenuItem[]>(() =>
    canShare.value
      ? [{ label: "Compartilhar esta leitura", icon: "i-lucide-share-2", onSelect: () => void shareReading() }]
      : [],
  );
}
