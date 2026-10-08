// "Compartilhar esta leitura" como item do ⋯ da página (as duas leituras da Produção).
// Antes era um botão próprio na barra do celular (`BiShareButton`), e ele, o ⋯ e o
// título não cabiam juntos em 390 px: o título cortava. O gesto é o mesmo: a folha de
// compartilhar do sistema (Web Share) com o título e o link, que já carrega o dia, a
// janela e os recortes; sem Web Share, copia o link.
import type { DropdownMenuItem } from "#ui/types";

export function useShareReading() {
  const { run: share } = usePendingAction(async () => {
    const url = window.location.href;
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: document.title, url });
        return;
      } catch (error) {
        if ((error as DOMException)?.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
    } catch {
      useSonner.warning("Não deu para compartilhar. O endereço na barra do navegador é o link desta leitura.");
    }
  });

  const shareItem: DropdownMenuItem = {
    label: "Compartilhar esta leitura",
    icon: "i-lucide-share-2",
    onSelect: () => void share(),
  };
  return { shareItem };
}
