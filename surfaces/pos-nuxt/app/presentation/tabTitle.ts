/**
 * O título da comanda na barra de contexto (v4, `pos-sale4.html`): "Mesa 6"
 * grande e "#1007" pequeno. O nome é como a mesa chama; o número é a referência
 * do balcão, do cupom e do quadro, e não some quando a comanda ganha nome.
 *
 * Sem nome próprio (o nome É o número), o título é "#1007" e não há o pequeno.
 */
export interface TabTitleView {
  title: string;
  /** "#1007" quando a comanda tem nome próprio; "" quando o título já é o número. */
  ref: string;
}

function normalize(value: string): string {
  return value.trim().replace(/^#/, "").replace(/^0+(?=\d)/, "").toLowerCase();
}

export function tabTitleView(display: string, number: string): TabTitleView {
  const name = (display || "").trim();
  const num = (number || "").trim().replace(/^#/, "");
  if (!name && !num) return { title: "#...", ref: "" };
  if (!name) return { title: `#${num}`, ref: "" };
  if (!num || normalize(name) === normalize(num)) {
    return { title: /^\d+$/.test(name) ? `#${name}` : name, ref: "" };
  }
  return { title: name, ref: `#${num}` };
}
