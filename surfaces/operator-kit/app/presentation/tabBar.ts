// O desenho da barra de baixo do celular, UM para a suíte: o exemplo oficial "With
// bottom tab bar" do NavigationMenu
// (https://ui.nuxt.com/docs/components/navigation-menu#with-bottom-tab-bar): ícone em
// cima, rótulo inteiro embaixo, ativo pelo `active` do item. Vale para a barra inferior
// do shell (`OperatorQuickBar`) e para a barra do polegar dos apps ainda fora do shell
// (`OperatorSectionBar`). Mora aqui, uma vez, nunca nas telas.
//
// Do kit somam-se: o alvo de toque mínimo (`min-h-control`), os itens espalhados por
// igual na largura (dono, 08/10: no exemplo literal eles se juntam no centro, longe do
// polegar) e o rótulo que QUEBRA em vez de cortar (o oficial leva `truncate`, e a
// 320 px a barra do Marketing dizia "De…", "Age…", "En…"; cópia da casa não se corta).
// O tamanho do rótulo é o valor da documentação, exceção declarada no teto da trava
// do conjunto mínimo (`guardrails.minimalSet.test.ts`).
export const TAB_BAR_UI = {
  // O Reka põe um <div> entre o root e a lista; ele precisa crescer para a lista
  // ocupar a largura (o root do Nuxt UI já mira esse filho com `[&>div]:min-w-0`).
  root: "justify-around border-t border-default py-2 [&>div]:flex-1",
  list: "w-full",
  item: "py-0 flex-1 min-w-0",
  link: "w-full flex-col gap-1 px-1 min-h-control justify-center",
  linkLeadingIcon: "size-5",
  linkLabel: "text-[10px]/3 font-normal text-clip whitespace-normal text-center break-words",
};
