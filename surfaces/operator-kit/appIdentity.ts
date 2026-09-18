import table from "./app-identity.json";

/**
 * IDENTIDADE DOS APPS DE OPERADOR — fonte única.
 *
 * Rótulo, símbolo e cor de um app estavam escritos em seis lugares (nuxt.config,
 * package.json, tools/pwa-gate, app.vue duas vezes, PWA_ICONS.md) e o inevitável
 * aconteceu: a Central tinha ícone cinza-ardósia e barra de título vinho, o Gestor se
 * chamava "Gestor" na janela e "Gestor de Pedidos" no launcher, a Cozinha era "KDS" no
 * título e "Cozinha" no rail. Agora tudo sai daqui.
 *
 * A tabela mora em `app-identity.json` — dado puro, que o `.mjs` do gerador de ícones e
 * o gate de PWA leem sem compilar TypeScript. Este módulo é a leitura tipada dela, e é
 * onde mora a prosa.
 *
 * Três regras que a tabela carrega:
 *
 *   1. **O rótulo é só o app.** O nome instalado é `"<casa> · <rótulo>"`, e a casa vem
 *      do `Shop.short_name` do Django em runtime — nunca do código. Separador é sempre
 *      o ponto médio; hífen na barra de título é o que o dono não quer ver.
 *   2. **A cor do app é UMA.** O mesmo `color` pinta o fundo do ícone gerado, a barra
 *      de título da janela do app instalado (`theme_color`) e a barra do navegador no
 *      Android. Ícone e janela não podem divergir: é por essa cor que o operador sabe
 *      em qual app está antes de ler qualquer palavra.
 *   3. **A tela de abertura é a tela do app.** O `background_color` do manifesto é o
 *      `--background` do tema do operador (`operator-theme.css`), claro ou escuro
 *      conforme o app. Valor avulso faz o splash piscar uma cor que nenhuma tela usa.
 */
export interface OperatorAppIdentity {
  /** Rótulo do app ("PDV"), e só ele: a casa entra em runtime. */
  label: string;
  /** Frase do manifesto. Sem o nome da casa — ela é dado do tenant. */
  description: string;
  /** Símbolo Iconify do ícone gerado (`<coleção>:<nome>`) — ver PWA_ICONS.md. */
  symbol: string;
  /**
   * Nome Lucide que o rail e o tile da Central mostram quando o PNG não carrega.
   * Igual ao `symbol` sem o prefixo, exceto na Produção: o `tabler:baguette` do PNG
   * não existe no Lucide e o fallback fica em `croissant`.
   */
  fallbackIcon: string;
  /** Cor de fundo do ícone = cor da barra de título do app instalado. */
  color: string;
  /**
   * Artigo definido do rótulo ("o PDV", "a Central", "as Compras"). Existe para que o
   * verbo fique no componente e a gramática no app: "Instale {artigo} {rótulo}".
   */
  article: string;
  /**
   * A frase do convite de instalação — o que ESTE app passa a fazer da tela inicial.
   * Os oito apps mostravam "Abra o caixa direto da tela inicial", copy do balcão, sob o
   * título "Instale Shopman" (o componente lia uma chave que o manifesto não tem e caía
   * no nome da marca). Como o benefício é de cada app, ele mora com a identidade.
   */
  install: string;
  /** App escuro por padrão (só a Cozinha): muda a tela de abertura, não a cor do app. */
  dark?: boolean;
}

export type OperatorAppRef = keyof typeof table.apps;

/** Desenho creme de todos os ícones da família. */
export const OPERATOR_ICON_FOREGROUND = table.foreground;

/** `?v=` dos PNGs. Sobe junto com a forma/desenho — ver PWA_ICONS.md. */
export const OPERATOR_ASSET_VERSION = table.assetVersion;

/** `--background` do `operator-theme.css`, nos dois temas. */
export const OPERATOR_CANVAS = table.canvas;

export const OPERATOR_APPS = table.apps as Record<OperatorAppRef, OperatorAppIdentity>;

export function operatorAppIdentity(app: string): OperatorAppIdentity {
  const identity = OPERATOR_APPS[app as OperatorAppRef];
  if (!identity) throw new TypeError(`app de operador desconhecido: ${app}`);
  return identity;
}

/** Os três PNGs que todo app de operador publica, iguais em todos — só o desenho muda. */
export function operatorAppIcons(version = OPERATOR_ASSET_VERSION) {
  return [
    { src: `/pwa/pwa-192x192.png?v=${version}`, sizes: "192x192", type: "image/png", purpose: "any" as const },
    { src: `/pwa/pwa-512x512.png?v=${version}`, sizes: "512x512", type: "image/png", purpose: "any" as const },
    { src: `/pwa/maskable-512x512.png?v=${version}`, sizes: "512x512", type: "image/png", purpose: "maskable" as const },
  ];
}

/** O ícone que o rail e o gate de login mostram como identidade do app. */
export function operatorAppIconSrc(version = OPERATOR_ASSET_VERSION): string {
  return `/pwa/pwa-64x64.png?v=${version}`;
}

/** Ícone de 192 px dos atalhos do manifesto — a mesma arte, no tamanho que o SO pede. */
export function operatorShortcutIconSrc(version = OPERATOR_ASSET_VERSION): string {
  return `/pwa/pwa-192x192.png?v=${version}`;
}
