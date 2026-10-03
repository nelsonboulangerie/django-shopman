// Gera src/pos-sale3.html, src/pos-sale3-tablet.html e src/pos-phone3.html
// usage: node gen-pos3.mjs && node build.mjs pos-sale3 pos-sale3-tablet pos-phone3
import fs from "node:fs";
const HERE = new URL(".", import.meta.url).pathname;
const W = (n, s) => fs.writeFileSync(`${HERE}src/${n}.html`, s);

const K = (t, cls = "") => `<kbd class="k ${cls}">${t}</kbd>`;
const STYLE = `<style>
  .k { font: 600 11px/1 ui-monospace, SFMono-Regular, monospace; padding: 3px 5px; border-radius: 4px; border: 1px solid var(--border); background: var(--muted); color: var(--muted-foreground); }
  .k-inv { border-color: color-mix(in oklab, var(--primary-foreground) 30%, transparent); background: color-mix(in oklab, var(--primary-foreground) 15%, transparent); color: var(--primary-foreground); }
  .tile-fb { position:relative; overflow:hidden; }
  .tile-fb::after { content:""; position:absolute; inset:0; background:radial-gradient(circle at 85% 15%, rgb(255 255 255 / .35), transparent 55%); }
  .fade-r { -webkit-mask-image: linear-gradient(90deg, #000 90%, transparent); mask-image: linear-gradient(90deg, #000 90%, transparent); }
  .measure { position:absolute; z-index:55; border-left:2px dashed #1f6feb; }
  .measure::before, .measure::after { content:""; position:absolute; left:-7px; width:12px; height:2px; background:#1f6feb; }
  .measure::before { top:0 } .measure::after { bottom:0 }
  .measure span { position:absolute; left:6px; top:50%; transform:translateY(-50%); background:#1f6feb; color:#fff; font:700 11px/16px "Instrument Sans",sans-serif; padding:2px 6px; border-radius:999px; white-space:nowrap; }
  .rail-ico { width:48px; height:48px; border-radius:12px; display:grid; place-items:center; position:relative; color: color-mix(in oklab, var(--rail-foreground) 82%, transparent); }
  .rail-ico svg { width:24px !important; height:24px !important; }
  .rail-ico.on { background: var(--rail-foreground); color: var(--rail); box-shadow: 0 1px 2px rgb(0 0 0/.18); }
  .rail-ico .badge { position:absolute; top:1px; right:0; min-width:18px; height:18px; padding:0 5px; border-radius:999px; background:#f2c46b; color:#3b2a1e; font-size:11px; line-height:18px; font-weight:700; text-align:center; }
  .rail-ico .attn { position:absolute; top:7px; right:8px; width:9px; height:9px; border-radius:999px; background:#f2c46b; box-shadow:0 0 0 2px var(--rail); }
  .stripes { background: repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in oklab, var(--destructive) 10%, transparent) 6px 12px); }
  .cam { background: radial-gradient(120% 80% at 50% 35%, #5b4a3c 0%, #2a211b 55%, #120d0a 100%); }
  .scan-corner { position:absolute; width:34px; height:34px; border-color:#7fe0a6; border-style:solid; }
</style>`;

// ---------- dados ----------
const TILES = [
  { n: "Croissant Tradicional", sku: "CROISSANT", p: "R$ 13,00", c: "#C58A2B", ink: "#9a6a1f", i: "croissant" },
  { n: "Pain au Chocolat", sku: "PAIN-CHOCOLAT", p: "R$ 15,00", c: "#C58A2B", ink: "#9a6a1f", i: "croissant" },
  { n: "Baguete Gergelim", sku: "BAGUETE-GERGELIM", p: "R$ 9,00 a 18,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat", grp: "2 tamanhos" },
  { n: "Baguette de Tradition", sku: "BAGUETTE-TRADITION", p: "R$ 16,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat" },
  { n: "Bichon au Citron", sku: "BICHON-CITRON", p: "R$ 18,00", c: "#B8577A", ink: "#8e3d5b", i: "cake-slice", out: 1 },
  { n: "Brioche Nanterre", sku: "BRIOCHE-NANTERRE", p: "R$ 22,00", c: "#C9A56A", ink: "#8a6c3a", i: "sandwich" },
  { n: "Shokupan", sku: "SHOKUPAN", p: "R$ 28,00", c: "#C9A56A", ink: "#8a6c3a", i: "sandwich" },
  { n: "Caffè Latte", sku: "CAFFE-LATTE", p: "R$ 14,00", c: "#8A5A3B", ink: "#6b4329", i: "coffee" },
  { n: "Madeleine", sku: "MADELEINE", p: "R$ 6,50", c: "#B8577A", ink: "#8e3d5b", i: "cake-slice" },
  { n: "Azeite Defumado 250ml", sku: "AZEITE-DEFUMADO-250", p: "R$ 143,00", c: "#5E7A4A", ink: "#46603a", i: "package", out: 1 },
  { n: "Mini Focaccia Cebola", sku: "MINI-FOCACCIA", p: "R$ 12,00", c: "#A95032", ink: "#7f3a22", i: "pizza" },
  { n: "Limonada Siciliana", sku: "LIMONADA-SIC", p: "R$ 11,00", c: "#3E7FA8", ink: "#2d5f80", i: "cup-soda" },
  { n: "Combo Café da Manhã", sku: "COMBO-CAFE", p: "R$ 24,00 a 32,00", c: "#7D4B88", ink: "#5e3767", i: "gift", grp: "3 opções" },
  { n: "Campagne Passas & Castanhas", sku: "CAMPAGNE-PASSAS", p: "R$ 33,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat" },
  { n: "Chausson aux Pommes", sku: "CHAUSSON-POMME", p: "R$ 16,00", c: "#C58A2B", ink: "#9a6a1f", i: "croissant" },
  { n: "Cappuccino", sku: "CAPPUCCINO", p: "R$ 14,00", c: "#8A5A3B", ink: "#6b4329", i: "coffee" },
  { n: "Brioche Chocolat", sku: "BRIOCHE-CHOCOLAT", p: "R$ 10,00", c: "#C9A56A", ink: "#8a6c3a", i: "sandwich" },
  { n: "Bâtard", sku: "BATARD", p: "R$ 13,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat" },
  { n: "Pão de Hambúrguer", sku: "PAO-HAMBURGUER", p: "R$ 8,00", c: "#C9A56A", ink: "#8a6c3a", i: "sandwich" },
  { n: "Chá Gelado Hibisco", sku: "CHA-HIBISCO", p: "R$ 12,00", c: "#3E7FA8", ink: "#2d5f80", i: "cup-soda" },
];

const EXTRA = [
  { n: "Baguete Lanche", sku: "BAGUETE-LANCHE", p: "R$ 9,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat" },
  { n: "Brioche Burger Bun", sku: "BRIOCHE-BURGER", p: "R$ 8,00", c: "#C9A56A", ink: "#8a6c3a", i: "sandwich" },
  { n: "Baguette Campagne", sku: "BAGUETTE-CAMPAGNE", p: "R$ 17,00", c: "#8C6A3F", ink: "#6e5230", i: "wheat" },
  { n: "Água com Gás", sku: "AGUA-GAS", p: "R$ 6,00", c: "#3E7FA8", ink: "#2d5f80", i: "cup-soda" },
  { n: "Pain aux Raisins", sku: "PAIN-RAISINS", p: "R$ 16,00", c: "#C58A2B", ink: "#9a6a1f", i: "croissant" },
];
function tile(t, { img = 96, pad = "px-3 py-2", name = "op-label", price = "op-title", extra = "" } = {}) {
  const grpShadow = t.grp ? " shadow-[4px_4px_0_-1px_var(--card),4px_4px_0_0_var(--border)]" : "";
  return `<button ${t.out ? "disabled " : ""}class="rounded-lg border border-border bg-card overflow-hidden text-left flex flex-col relative${grpShadow} ${extra}">
  <div class="tile-fb h-[${img}px] grid place-items-center${t.out ? " opacity-55" : ""}" style="background:color-mix(in oklab,${t.c} 20%,var(--card))">
    <span style="color:${t.ink}" class="grid place-items-center"><i data-i="${t.i}" class="size-9"></i></span>
    <span class="absolute left-2 bottom-1.5 font-mono text-[10px] tracking-wide" style="color:${t.ink}">${t.sku}</span>
    ${t.grp ? `<span class="absolute right-2 top-2 h-6 px-2 rounded-full bg-card/90 op-micro font-semibold inline-flex items-center gap-1"><i data-i="layers" class="size-3.5"></i>${t.grp}</span>` : ""}
  </div>
  <div class="${pad} flex flex-col gap-0.5">
    <span class="${name} font-semibold truncate${t.out ? " text-muted-foreground" : ""}">${t.n.replace("&", "&amp;")}</span>
    ${t.out
      ? `<span class="flex items-center justify-between"><span class="${price} tnum text-muted-foreground">${t.p}</span><span class="h-6 px-2 rounded-full bg-muted text-muted-foreground op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-muted-foreground"></span>Esgotado</span></span>`
      : `<span class="${price} tnum">${t.p}</span>`}
  </div>
</button>`;
}

const LINES = [
  { q: 2, n: "Croissant Tradicional", u: "R$ 13,00", t: "R$ 26,00" },
  { q: 1, n: "Pain au Chocolat", u: "R$ 15,00", t: "R$ 15,00", on: 1 },
  { q: 1, n: "Baguette de Tradition", u: "R$ 16,00", t: "R$ 16,00" },
  { q: 2, n: "Cappuccino", u: "R$ 14,00", t: "R$ 28,00", obs: "1 sem açúcar" },
  { q: 1, n: "Bichon au Citron", u: "R$ 18,00", t: "R$ 18,00" },
  { q: 1, n: "Madeleine", u: "R$ 6,50", t: "R$ 6,50" },
  { q: 1, n: "Caffè Latte", u: "R$ 14,00", t: "R$ 14,00" },
  { q: 1, n: "Shokupan", u: "R$ 28,00", t: "R$ 28,00" },
  { q: 1, n: "Brioche Nanterre", u: "R$ 22,00", t: "R$ 22,00" },
  { q: 1, n: "Mini Focaccia Cebola", u: "R$ 12,00", t: "R$ 12,00" },
];
const TOTAL = "R$ 185,50"; // 26+15+16+28+18+6,5+14+28+22+12
const ITEMS = 12;

const CHIPS = [
  ["Bebidas geladas", "#3E7FA8"], ["Bebidas quentes", "#8A5A3B"], ["Combos", "#7D4B88"], ["Doces", "#B8577A"],
  ["Folhados", "#C58A2B"], ["Macios", "#C9A56A"], ["Mercearia", "#5E7A4A"], ["Rústicos", "#8C6A3F"], ["Salgados", "#A95032"],
];

// ===================================================================
// 1) DESKTOP
// ===================================================================
function lineDesktop(l) {
  const sub = `<p class="op-micro text-muted-foreground tnum truncate">${l.u} cada${l.obs ? ` · <span class="text-foreground/80">Obs.: ${l.obs}</span>` : ""}</p>`;
  if (!l.on) return `<li class="h-[54px] shrink-0 px-3 border-b border-border flex items-center gap-2">
    <span class="op-title tnum w-7">${l.q}×</span>
    <div class="flex-1 min-w-0"><p class="op-body font-medium truncate leading-5">${l.n}</p>${sub}</div>
    <span class="op-title tnum">${l.t}</span>
  </li>`;
  return `<li class="shrink-0 px-3 pt-[9px] pb-2.5 border-b border-border bg-primary/6 shadow-[inset_3px_0_0_var(--primary)] flex flex-col gap-2">
    <div class="flex items-center gap-2">
      <span class="op-title tnum w-7">${l.q}×</span>
      <div class="flex-1 min-w-0"><p class="op-body font-medium truncate leading-5">${l.n}</p>${sub}</div>
      <span class="op-title tnum">${l.t}</span>
    </div>
    <div class="flex items-center gap-2 pl-9">
      <div class="h-9 inline-flex items-center rounded-md border border-input bg-card overflow-hidden">
        <button class="size-9 grid place-items-center border-r border-border" title="Menos (−)"><i data-i="minus" class="size-4"></i></button>
        <span class="w-9 text-center op-title tnum">1</span>
        <button class="size-9 grid place-items-center border-l border-border" title="Mais (+)"><i data-i="plus" class="size-4"></i></button>
      </div>
      <div class="flex-1"></div>
      <button class="h-9 px-2.5 rounded-md inline-flex items-center gap-1.5 op-label text-destructive hover:bg-destructive/10"><i data-i="trash-2" class="size-4"></i>Remover ${K("Del")}</button>
    </div>
  </li>`;
}

const railDesktop = `<aside class="w-[76px] shrink-0 bg-rail text-rail-foreground flex flex-col items-center gap-1 pb-2">
    {{> rail3top app="PDV" icon="shopping-basket"}}
    <a class="rail-item on"><i data-i="receipt"></i>Comandas<kbd>F2</kbd><span class="badge">1</span></a>
    <a class="rail-item"><i data-i="calendar-clock"></i>Encomendas<span class="badge">4</span></a>
    <a class="rail-item" title="Caixa: sangria recomendada (gaveta acima do limite)"><i data-i="wallet"></i>Caixa<span class="attn"></span></a>
    <a class="rail-item" title="Abre a tela do cliente no segundo monitor"><i data-i="monitor-smartphone"></i>Tela do cliente</a>
    <div class="flex-1"></div>
    <a class="rail-item bg-rail-foreground/12" title="Terminal PDV-01: fiscal em contingência"><i data-i="cpu"></i>Terminal<span class="attn"></span></a>
    <div class="w-9 h-px bg-rail-foreground/20 my-1"></div>
    <a class="rail-item" title="Avisos"><i data-i="bell"></i>Avisos<span class="badge">2</span></a>
    <a class="rail-item" title="Atalhos (?)"><i data-i="keyboard"></i>Atalhos</a>
    <a class="rail-item" title="Bloquear"><i data-i="lock"></i>Bloquear</a>
    <div class="size-10 my-2 rounded-full bg-rail-foreground/15 grid place-items-center text-[13px] font-semibold text-rail-foreground" title="Marta (caixa 1)">MC</div>
  </aside>`;

const termRow = (ic, name, state, tone, note = "") => `<div class="h-11 px-2 rounded-md flex items-center gap-3">
  <span class="relative size-8 rounded-md bg-muted grid place-items-center"><i data-i="${ic}" class="size-4"></i><span class="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full bg-${tone} ring-2 ring-popover"></span></span>
  <div class="flex-1 min-w-0"><p class="op-label font-semibold">${name}</p>${note ? `<p class="op-micro text-muted-foreground truncate">${note}</p>` : ""}</div>
  <span class="h-6 px-2 rounded-full bg-${tone}/12 text-${tone} op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-${tone}"></span>${state}</span>
</div>`;

const desktop = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="1440x900">${STYLE}</head>
<body class="bg-background text-foreground font-sans antialiased" data-app="pos">
<div class="flex h-[900px] overflow-hidden relative">
  ${railDesktop}
  <main class="flex-1 flex flex-col min-w-0">
    <!-- UMA barra: contexto do pedido -->
    <header class="h-14 shrink-0 px-3 flex items-center gap-2 border-b border-border bg-card">
      <button class="size-10 rounded-md border border-border bg-card grid place-items-center" title="Voltar às comandas (Esc)"><i data-i="arrow-left" class="size-5"></i></button>
      <div class="h-10 p-1 rounded-md bg-secondary inline-flex items-center gap-1" role="radiogroup">
        <button class="h-full px-2.5 rounded inline-flex items-center gap-1.5 op-label text-muted-foreground"><i data-i="store" class="size-4"></i>Balcão</button>
        <button class="h-full px-2.5 rounded bg-card shadow-sm inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="calendar-clock" class="size-4"></i>Encomendas</button>
      </div>
      <button class="h-10 px-2 rounded-md inline-flex items-center gap-1.5" title="Renomear comanda"><span class="op-figure !text-[22px]">#1007</span><i data-i="pencil" class="size-3.5 text-muted-foreground"></i></button>
      <div class="w-px h-6 bg-border"></div>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label" title="Cliente (F6)"><i data-i="user-round" class="size-4 text-muted-foreground"></i><span class="font-semibold">Maria Santos</span>${K("F6")}</button>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label" title="Recebimento (F7)"><i data-i="store" class="size-4 text-muted-foreground"></i><span class="font-semibold">Retirada na loja</span>${K("F7")}</button>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label" title="Quando (F8), só em Encomendas"><i data-i="calendar-clock" class="size-4 text-primary"></i><span class="font-semibold">Sáb 04/10 às 09:00</span>${K("F8", "bg-card")}</button>
      <span class="h-6 px-2 rounded-full bg-warning/12 text-warning op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-warning"></span>PIX aguardando</span>
      <div class="flex-1"></div>
      <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum px-1" title="Ao vivo · última leitura 22:03:14"><span class="live-dot"></span>22:03</span>
      <button class="size-10 rounded-md border border-border bg-card grid place-items-center" title="Últimas vendas"><i data-i="history" class="size-5"></i></button>
      <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label text-muted-foreground" title="Liberar comanda (pede confirmação)"><i data-i="x" class="size-4"></i>Liberar comanda</button>
    </header>

    <div class="flex-1 flex min-h-0">
      <!-- Produtos -->
      <section class="flex-1 min-w-0 flex flex-col">
        <div class="px-3 pt-2.5 pb-2 flex items-center gap-2">
          <label class="h-11 flex-1 px-3 rounded-md border-2 border-primary bg-card inline-flex items-center gap-2.5 shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_14%,transparent)]" title="Uma busca só: produtos primeiro, depois comandas, clientes e encomendas">
            <i data-i="search" class="size-5 text-muted-foreground"></i>
            <span class="flex-1 op-body text-muted-foreground truncate">Buscar produto, código, comanda ou cliente</span>
            <span class="op-micro text-muted-foreground">Enter adiciona</span>
            ${K("F3")}${K("/")}
          </label>
          <div class="h-11 p-1 rounded-md bg-secondary inline-flex items-center gap-1" role="radiogroup" title="Densidade da grade">
            <button class="h-full w-9 rounded grid place-items-center text-muted-foreground" title="Compacta"><i data-i="grid-3x3" class="size-4"></i></button>
            <button class="h-full px-2 rounded bg-card shadow-sm inline-flex items-center gap-1.5 op-label font-semibold" title="Padrão"><i data-i="layout-grid" class="size-4"></i>Padrão</button>
            <button class="h-full w-9 rounded grid place-items-center text-muted-foreground" title="Ampla"><i data-i="grid-2x2" class="size-4"></i></button>
          </div>
        </div>
        <div class="px-3 pb-2.5 flex items-center gap-1 overflow-hidden fade-r">
          <button class="h-8 px-2.5 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-1.5 op-label font-semibold shrink-0"><i data-i="check" class="size-3.5 text-primary"></i>Tudo</button>
          ${CHIPS.map(([n, c]) => `<button class="h-8 px-2.5 rounded-full border border-border bg-card inline-flex items-center gap-1.5 op-label shrink-0"><span class="size-2 rounded-full" style="background:${c}"></span>${n}</button>`).join("\n          ")}
        </div>
        <div class="flex-1 overflow-hidden px-3 grid grid-cols-5 auto-rows-max gap-2.5 content-start">
          ${[...TILES, ...EXTRA].map((t) => tile(t, { img: 92 })).join("\n")}
        </div>
      </section>

      <!-- Carrinho -->
      <aside class="w-[392px] shrink-0 border-l border-border bg-card flex flex-col">
        <div class="h-10 shrink-0 px-3 flex items-center gap-2 border-b border-border">
          <h2 class="op-title">${ITEMS} itens</h2><span class="op-micro text-muted-foreground">em ${LINES.length} linhas</span>
          <div class="flex-1"></div>
          <button class="h-8 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label"><i data-i="list-checks" class="size-4"></i>Selecionar${K("Alt S")}</button>
        </div>
        <ul class="flex-1 min-h-0 overflow-hidden flex flex-col">
          ${LINES.map(lineDesktop).join("\n")}
        </ul>
        <!-- teclado recolhido: teclado físico detectado -->
        <div class="h-11 shrink-0 px-2 flex items-center gap-1.5 border-t border-border bg-muted/50" title="Teclado físico detectado: digite o número e escolha o campo. O teclado da tela fica recolhido.">
          <i data-i="keyboard" class="size-4 text-muted-foreground ml-1"></i>
          <div class="min-w-0 flex-1 leading-none">
            <p class="op-micro text-muted-foreground truncate">Digite no teclado</p>
            <p class="op-label font-semibold truncate">Pain au Chocolat</p>
          </div>
          <div class="h-8 p-0.5 rounded-md bg-secondary inline-flex items-center gap-0.5">
            <span class="h-full px-2 rounded bg-primary text-primary-foreground op-micro font-semibold inline-flex items-center">Qtd</span>
            <span class="h-full px-1.5 rounded op-micro font-semibold text-muted-foreground inline-flex items-center">Desc %</span>
            <span class="h-full px-1.5 rounded op-micro font-semibold text-muted-foreground inline-flex items-center">Desc R$</span>
            <span class="h-full px-1.5 rounded op-micro font-semibold text-muted-foreground inline-flex items-center">Obs.</span>
          </div>
          <button class="h-8 w-8 rounded-md border border-border bg-card grid place-items-center" title="Mostrar teclado da tela"><i data-i="chevron-up" class="size-4"></i></button>
        </div>
        <!-- rodapé: 2 linhas, 112 px -->
        <div class="h-[112px] shrink-0 px-3 py-2 border-t border-border flex flex-col gap-2">
          <div class="grid grid-cols-2 gap-2">
            <button class="h-10 rounded-md border border-primary bg-card inline-flex items-center justify-center gap-1.5 op-label font-semibold"><i data-i="utensils-crossed" class="size-4"></i>Enviar à cozinha<span class="min-w-5 h-5 px-1 rounded-full bg-primary text-primary-foreground text-[11px] grid place-items-center tnum">${ITEMS}</span>${K("F9")}</button>
            <button class="h-10 rounded-md border border-border bg-card inline-flex items-center justify-center gap-1.5 op-label font-semibold"><i data-i="split" class="size-4"></i>Transferir${K("F10")}</button>
          </div>
          <div class="flex items-center gap-3">
            <div class="flex flex-col leading-none">
              <span class="op-micro text-muted-foreground">Total parcial</span>
              <span class="text-[26px] leading-8 font-semibold tnum">${TOTAL}</span>
            </div>
            <button class="h-12 flex-1 rounded-md bg-primary text-primary-foreground inline-flex items-center justify-center gap-2 op-title"><i data-i="credit-card" class="size-5"></i>Pagamento${K("F4", "k-inv")}</button>
          </div>
        </div>
      </aside>
    </div>
  </main>

  <!-- popover do Terminal (aberto para mostrar) -->
  <div class="absolute z-30 left-[84px] top-[470px] w-[340px] rounded-xl border border-border bg-popover shadow-2xl">
    <div class="px-3 pt-3 pb-2 flex items-center gap-2 border-b border-border">
      <i data-i="cpu" class="size-4 text-muted-foreground"></i><p class="op-title">Terminal PDV-01</p>
      <span class="ml-auto op-micro text-muted-foreground">lido 22:03</span>
    </div>
    <div class="p-1.5">
      ${termRow("cpu", "Agente local", "Conectado", "success")}
      ${termRow("printer", "Impressora", "Pronta", "success")}
      ${termRow("archive", "Gaveta", "Fechada", "success")}
      ${termRow("file-text", "Fiscal (NFC-e)", "Contingência", "warning", "Emite ao reconectar")}
    </div>
    <div class="px-3 h-12 flex items-center gap-2 border-t border-border">
      <span class="op-micro text-muted-foreground">Tela do cliente: monitor 2</span>
      <button class="ml-auto h-9 px-3 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="refresh-cw" class="size-4"></i>Atualizar${K("R")}</button>
    </div>
    <span class="absolute -left-[7px] top-[150px] size-3 rotate-45 bg-popover border-l border-b border-border"></span>
  </div>

  <!-- medida -->
  <div class="note" style="all:unset"><div class="measure" style="left:1044px;top:96px;height:648px"><span style="left:12px;top:auto;bottom:16px;transform:none">lista de itens: 648 px (y 96 a 744) · 10 linhas, cabe mais 1</span></div></div>

  <span class="pin" style="left:24px;top:36px">1</span>
  <span class="pin" style="left:850px;top:44px">2</span>
  <span class="pin" style="left:44px;top:600px">3</span>
  <span class="pin" style="left:90px;top:2px">4</span>
  <span class="pin" style="left:1150px;top:30px">5</span>
  <span class="pin" style="left:90px;top:60px">6</span>
  <span class="pin" style="left:1050px;top:62px">7</span>
  <span class="pin" style="left:1050px;top:748px">8</span>
</div>
<div class="legend">
  <p class="t">PDV · Venda · v3 <span>desktop com teclado físico · a lista de itens ganha a altura que a v2 tinha tirado</span></p>
  <div><b>1</b>Selo do PDV troca de app. As seções voltam para o rail: Comandas F2 (1), Encomendas (4), Caixa (ponto quando pede sangria), Tela do cliente (abre no monitor 2).</div>
  <div><b>2</b>A barra de seções e a faixa global somem: o topo tem UMA barra de 56 px, só com o contexto do pedido.</div>
  <div><b>3</b>Terminal no pé do rail com ponto de atenção; o painel mostra agente, impressora, gaveta e fiscal e guarda o Atualizar (R). Avisos, Atalhos e Bloquear abaixo.</div>
  <div><b>4</b>Voltar (Esc), Balcão | Encomendas, #1007 renomeável. Em Encomendas aparece Quando F8 ao lado de Cliente F6 e Recebimento F7.</div>
  <div><b>5</b>PIX aguardando como pílula; ao vivo vira ponto + hora; Últimas vendas e Liberar comanda à direita.</div>
  <div><b>6</b>Busca F3 (ou /) é a busca única: produtos primeiro, Enter adiciona; logo abaixo, comandas, clientes e encomendas. Densidade e coleções em 2 linhas compactas.</div>
  <div><b>7</b>Lista de itens: hoje 485 px (y 60 a 545), v2 275 px (y 190 a 465), v3 648 px (y 96 a 744). Linhas visíveis: hoje ~8, v2 ~4, v3 10 (12 itens) com a linha ativa aberta.</div>
  <div><b>8</b>Teclado físico detectado: o numérico da tela recolhe numa faixa de 44 px (linha ativa, Qtd | Desc % | Desc R$ | Obs.); as teclas físicas seguem iguais. Rodapé de 112 px: F9, F10, total e Pagamento F4.</div>
</div>
</body></html>`;
W("pos-sale3", desktop);

// ===================================================================
// 2) TABLET
// ===================================================================
function lineTablet(l, i) {
  const sub = `<p class="op-micro text-muted-foreground tnum truncate">${l.u} cada${l.obs ? ` · <span class="text-foreground/80">Obs.: ${l.obs}</span>` : ""}</p>`;
  if (l.on) return `<li class="shrink-0 px-3 pt-2 pb-2.5 border-b border-border bg-primary/6 shadow-[inset_3px_0_0_var(--primary)] flex flex-col gap-2">
    <div class="h-10 flex items-center gap-2">
      <span class="op-title tnum w-7">${l.q}×</span>
      <div class="flex-1 min-w-0"><p class="op-body font-medium truncate leading-5">${l.n}</p>${sub}</div>
      <span class="op-title tnum">${l.t}</span>
    </div>
    <div class="flex items-center gap-2 pl-9">
      <div class="h-12 inline-flex items-center rounded-md border border-input bg-card overflow-hidden">
        <button class="size-12 grid place-items-center border-r border-border"><i data-i="minus" class="size-5"></i></button>
        <span class="w-11 text-center op-title tnum">1</span>
        <button class="size-12 grid place-items-center border-l border-border"><i data-i="plus" class="size-5"></i></button>
      </div>
      <div class="flex-1"></div>
      <button class="h-12 px-3 rounded-md inline-flex items-center gap-1.5 op-label text-destructive"><i data-i="trash-2" class="size-5"></i>Remover</button>
    </div>
  </li>`;
  if (l.swipe) return `<li class="h-14 shrink-0 border-b border-border relative overflow-hidden bg-destructive">
    <div class="absolute inset-y-0 right-0 w-[104px] grid place-items-center text-white"><span class="flex flex-col items-center gap-0.5 op-micro font-semibold"><i data-i="trash-2" class="size-5"></i>Remover</span></div>
    <div class="absolute inset-0 bg-card px-3 flex items-center gap-2 shadow-[6px_0_12px_rgb(0_0_0/.14)]" style="transform:translateX(-104px)">
      <span class="op-title tnum w-7">${l.q}×</span>
      <div class="flex-1 min-w-0"><p class="op-body font-medium truncate leading-5">${l.n}</p>${sub}</div>
      <span class="op-title tnum">${l.t}</span>
    </div>
  </li>`;
  return `<li class="h-14 shrink-0 px-3 border-b border-border flex items-center gap-2">
    <span class="op-title tnum w-7">${l.q}×</span>
    <div class="flex-1 min-w-0"><p class="op-body font-medium truncate leading-5">${l.n}</p>${sub}</div>
    <span class="op-title tnum">${l.t}</span>
  </li>`;
}
const TLINES = LINES.map((l, i) => (i === 3 ? { ...l, swipe: 1 } : l));
const key = (t, cls = "bg-background border border-border op-title tnum") => `<button class="h-[52px] rounded-md ${cls}">${t}</button>`;

const railTablet = `<aside class="w-16 shrink-0 bg-rail text-rail-foreground flex flex-col items-center gap-1.5 py-2">
  <button class="size-12 rounded-xl grid place-items-center relative mb-1" style="background:var(--app-color)" title="PDV: trocar de app"><i data-i="shopping-basket" class="size-6 text-white"></i><span class="absolute -bottom-1 -right-1 size-5 rounded-full bg-rail-foreground grid place-items-center shadow"><i data-i="layout-grid" class="size-3 text-rail"></i></span></button>
  <div class="w-8 h-px bg-rail-foreground/20 my-1"></div>
  <a class="rail-ico on" title="Comandas"><i data-i="receipt"></i><span class="badge">1</span></a>
  <a class="rail-ico" title="Encomendas"><i data-i="calendar-clock"></i><span class="badge">4</span></a>
  <a class="rail-ico" title="Caixa"><i data-i="wallet"></i><span class="attn"></span></a>
  <a class="rail-ico" title="Tela do cliente"><i data-i="monitor-smartphone"></i></a>
  <div class="flex-1"></div>
  <a class="rail-ico" title="Terminal"><i data-i="cpu"></i><span class="attn"></span></a>
  <a class="rail-ico" title="Avisos"><i data-i="bell"></i><span class="badge">2</span></a>
  <a class="rail-ico" title="Bloquear"><i data-i="lock"></i></a>
  <div class="size-10 mt-1 rounded-full bg-rail-foreground/15 grid place-items-center text-[13px] font-semibold text-rail-foreground">MC</div>
</aside>`;

const tabletScreen = `<div class="flex h-full bg-background text-foreground">
  ${railTablet}
  <main class="flex-1 flex flex-col min-w-0">
    <header class="h-14 shrink-0 px-2 flex items-center gap-2 border-b border-border bg-card">
      <button class="size-12 rounded-md border border-border bg-card grid place-items-center"><i data-i="arrow-left" class="size-5"></i></button>
      <div class="h-12 p-1 rounded-md bg-secondary inline-flex items-center gap-1">
        <button class="h-full px-3 rounded inline-flex items-center gap-1.5 op-label text-muted-foreground"><i data-i="store" class="size-4"></i>Balcão</button>
        <button class="h-full px-3 rounded bg-card shadow-sm inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="calendar-clock" class="size-4"></i>Encomendas</button>
      </div>
      <button class="h-12 px-2 rounded-md inline-flex items-center gap-1.5"><span class="op-figure !text-[22px]">#1007</span><i data-i="pencil" class="size-4 text-muted-foreground"></i></button>
      <div class="w-px h-7 bg-border"></div>
      <button class="h-12 px-3 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label"><i data-i="user-round" class="size-4 text-muted-foreground"></i><span class="font-semibold">Maria Santos</span></button>
      <button class="h-12 px-3 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label"><i data-i="store" class="size-4 text-muted-foreground"></i><span class="font-semibold">Retirada na loja</span></button>
      <button class="h-12 px-3 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label"><i data-i="calendar-clock" class="size-4 text-primary"></i><span class="font-semibold">Sáb 04/10 · 09:00</span></button>
      <div class="flex-1"></div>
      <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum"><span class="live-dot"></span>22:03</span>
      <button class="size-12 rounded-md border border-border bg-card grid place-items-center" title="Últimas vendas"><i data-i="history" class="size-5"></i></button>
      <button class="size-12 rounded-md border border-border bg-card grid place-items-center" title="Mais: Liberar comanda"><i data-i="ellipsis-vertical" class="size-5"></i></button>
    </header>
    <div class="flex-1 flex min-h-0">
      <section class="flex-1 min-w-0 flex flex-col">
        <div class="px-3 pt-3 pb-2 flex items-center gap-2">
          <label class="h-12 flex-1 px-3 rounded-md border border-input bg-card inline-flex items-center gap-2.5">
            <i data-i="search" class="size-5 text-muted-foreground"></i>
            <span class="flex-1 op-body text-muted-foreground truncate">Buscar produto, comanda ou cliente</span>
          </label>
          <button class="size-12 rounded-md border border-border bg-card grid place-items-center" title="Ler código de barras com a câmera"><i data-i="scan-barcode" class="size-5"></i></button>
          <div class="h-12 p-1 rounded-md bg-secondary inline-flex items-center gap-1">
            <button class="h-full w-10 rounded grid place-items-center text-muted-foreground"><i data-i="grid-3x3" class="size-5"></i></button>
            <button class="h-full w-10 rounded bg-card shadow-sm grid place-items-center"><i data-i="layout-grid" class="size-5"></i></button>
          </div>
        </div>
        <div class="px-3 pb-3 flex items-center gap-1.5 overflow-hidden fade-r">
          <button class="h-11 px-3.5 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-1.5 op-label font-semibold shrink-0"><i data-i="check" class="size-4 text-primary"></i>Tudo</button>
          ${CHIPS.map(([n, c]) => `<button class="h-11 px-3.5 rounded-full border border-border bg-card inline-flex items-center gap-1.5 op-label shrink-0"><span class="size-2 rounded-full" style="background:${c}"></span>${n}</button>`).join("\n          ")}
        </div>
        <div class="flex-1 overflow-hidden px-3 grid grid-cols-3 auto-rows-max gap-3 content-start relative">
          ${TILES.slice(0, 12).map((t, i) => tile(t, { img: 112, pad: "px-3.5 py-3", name: "op-body", price: "op-title", extra: i === 2 ? "ring-4 ring-primary/35" : "" })).join("\n")}
          <!-- pressão longa: opções -->
          <div class="absolute z-20 left-[424px] top-[150px] w-[300px] rounded-xl border border-border bg-popover shadow-2xl overflow-hidden">
            <div class="px-4 pt-3 pb-2 flex items-center gap-2 border-b border-border"><i data-i="wheat" class="size-4 text-muted-foreground"></i><p class="op-title">Baguete Gergelim</p><span class="ml-auto op-micro text-muted-foreground">pressão longa</span></div>
            <div class="p-2 grid grid-cols-2 gap-2">
              <button class="h-14 rounded-md border border-border bg-card flex flex-col items-center justify-center"><span class="op-label font-semibold">Pequena</span><span class="op-micro text-muted-foreground tnum">R$ 9,00</span></button>
              <button class="h-14 rounded-md border border-border bg-card flex flex-col items-center justify-center"><span class="op-label font-semibold">Grande</span><span class="op-micro text-muted-foreground tnum">R$ 18,00</span></button>
            </div>
            <button class="w-full h-12 px-4 border-t border-border inline-flex items-center gap-2 op-label"><i data-i="message-square-text" class="size-4"></i>Adicionar com observação</button>
            <button class="w-full h-12 px-4 border-t border-border inline-flex items-center gap-2 op-label"><i data-i="hash" class="size-4"></i>Adicionar várias (quantidade)</button>
          </div>
        </div>
      </section>
      <aside class="w-[384px] shrink-0 border-l border-border bg-card flex flex-col">
        <div class="h-12 shrink-0 pl-3 flex items-center gap-2 border-b border-border">
          <h2 class="op-title">${ITEMS} itens</h2>
          <span class="h-6 px-2 rounded-full bg-warning/12 text-warning op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-warning"></span>PIX aguardando</span>
          <div class="flex-1"></div>
          <button class="h-12 px-3 border-l border-border inline-flex items-center gap-2 op-label"><i data-i="list-checks" class="size-5"></i>Selecionar</button>
        </div>
        <ul class="flex-1 min-h-0 overflow-hidden flex flex-col relative">
          ${TLINES.map(lineTablet).join("\n")}
          
        </ul>
        <div class="shrink-0 px-2.5 py-1.5 border-t border-border bg-muted/40">
          <div class="grid grid-cols-4 gap-1.5">
            ${key("1")}${key("2")}${key("3")}${key("Qtd", "bg-primary text-primary-foreground op-label font-semibold")}
            ${key("4")}${key("5")}${key("6")}${key("Desc %", "bg-secondary border border-border op-label font-semibold")}
            ${key("7")}${key("8")}${key("9")}${key("Desc R$", "bg-secondary border border-border op-label font-semibold")}
            ${key("0")}${key(",")}${key(`<span class="grid place-items-center text-destructive"><i data-i="delete" class="size-5"></i></span>`, "bg-background border border-border")}${key("Obs.", "bg-secondary border border-border op-label font-semibold")}
          </div>
        </div>
        <div class="shrink-0 px-2.5 py-2 border-t border-border flex gap-2">
          <button class="h-14 w-[76px] shrink-0 rounded-md border border-border bg-card flex flex-col items-center justify-center gap-0.5 op-micro font-semibold"><i data-i="split" class="size-5"></i>Transferir</button>
          <button class="h-14 px-3 shrink-0 rounded-md border border-primary bg-card inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="utensils-crossed" class="size-5"></i>Cozinha<span class="min-w-5 h-5 px-1 rounded-full bg-primary text-primary-foreground text-[11px] grid place-items-center tnum">${ITEMS}</span></button>
          <button class="h-14 flex-1 rounded-md bg-primary text-primary-foreground flex items-center justify-center gap-2.5"><i data-i="credit-card" class="size-5"></i><span class="flex flex-col items-start leading-none"><span class="op-micro opacity-85">Pagamento</span><span class="text-[20px] leading-6 font-semibold tnum">${TOTAL}</span></span></button>
        </div>
      </aside>
    </div>
  </main>
</div>`;

const tablet = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="1260x900">${STYLE}</head>
<body class="font-sans antialiased" data-app="pos" style="background:#e9dfd6">
<div class="h-[900px] relative grid place-items-center">
  <div class="device tablet"><div class="screen" style="width:1180px;height:820px">${tabletScreen}</div></div>
  <span class="pin" style="left:44px;top:120px">1</span>
  <span class="pin" style="left:990px;top:56px">2</span>
  <span class="pin" style="left:520px;top:118px">3</span>
  <span class="pin" style="left:800px;top:330px">4</span>
  <span class="pin" style="left:1200px;top:380px">5</span>
  <span class="pin" style="left:820px;top:604px">6</span>
  <span class="pin" style="left:820px;top:786px">7</span>
</div>
<div class="legend">
  <p class="t">PDV · Venda · tablet deitado (1180 × 820) <span>toque: sem teclas impressas, alvos de 48 px, numérico na tela</span></p>
  <div><b>1</b>Rail só de ícones (64 px) para ganhar largura: Comandas, Encomendas, Caixa, Tela do cliente; Terminal, Avisos e Bloquear no pé. Atalhos sai (não há teclado).</div>
  <div><b>2</b>A mesma barra de contexto, com alvos de 48 px e sem F6/F7/F8. Liberar comanda vai para o ⋮; PIX aguardando desce para o cabeçalho do carrinho.</div>
  <div><b>3</b>Busca única com botão de câmera para ler o código de barras de mercearia. Grade em 3 colunas com tiles maiores para o dedo.</div>
  <div><b>4</b>Pressão longa no tile abre as opções (tamanho, observação, quantidade). Toque simples adiciona.</div>
  <div><b>5</b>Deslizar a linha para a esquerda revela Remover (a dica aparece na primeira vez). Lista de 406 px (hoje 405 px) com o numérico na tela: 6 linhas com a ativa aberta. Total entra no botão Pagamento.</div>
  <div><b>6</b>Numérico visível porque toque não tem teclado: 4 × 4 teclas de 52 px (Qtd, Desc %, Desc R$, Obs. na quarta coluna).</div>
  <div><b>7</b>useOperatorContext: ponteiro grosso → esconde teclas e mostra o numérico. Se um teclado físico for conectado, as teclas voltam e o numérico recolhe como no desktop.</div>
</div>
</body></html>`;
W("pos-sale3-tablet", tablet);

// ===================================================================
// 3) PHONE
// ===================================================================
const statusBar = (dark = false) => `<div class="h-11 shrink-0 px-7 flex items-center justify-between text-[14px] font-semibold ${dark ? "text-white" : "text-foreground"}">
  <span class="tnum">09:02</span>
  <span class="inline-flex items-center gap-1.5"><i data-i="signal" class="size-4"></i><i data-i="wifi" class="size-4"></i><i data-i="battery-full" class="size-5"></i></span>
</div>`;
const homeBar = (dark = false) => `<div class="h-5 shrink-0 grid place-items-center"><span class="w-32 h-1 rounded-full ${dark ? "bg-white/70" : "bg-foreground/80"}"></span></div>`;

const pill = (tone, t) => tone === "muted" ? `<span class="h-6 px-2 rounded-full bg-muted text-muted-foreground op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-muted-foreground"></span>${t}</span>` : `<span class="h-6 px-2 rounded-full bg-${tone}/12 text-${tone} op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-${tone}"></span>${t}</span>`;
const pcard = ({ time, who, mode, mi, items, total, s1, l1, s2, l2, sel }) => `<div class="rounded-xl border ${sel ? "border-primary ring-2 ring-primary/25" : "border-border"} bg-card p-3 flex gap-3">
  <div class="w-14 shrink-0 flex flex-col items-center justify-center rounded-lg bg-secondary py-2"><span class="text-[18px] leading-6 font-semibold tnum">${time}</span><span class="op-micro text-muted-foreground">hoje</span></div>
  <div class="flex-1 min-w-0 flex flex-col gap-1">
    <div class="flex items-center gap-2"><p class="op-title truncate">${who}</p><span class="ml-auto op-title tnum">${total}</span></div>
    <p class="text-[13px] leading-5 text-muted-foreground truncate inline-flex items-center gap-1"><i data-i="${mi}" class="size-3.5"></i>${mode} · ${items}</p>
    <div class="flex items-center gap-1.5">${pill(s1, l1)}${pill(s2, l2)}</div>
  </div>
</div>`;

const phoneA = `<div class="h-full flex flex-col bg-background text-foreground">
  ${statusBar()}
  <div class="h-14 shrink-0 px-3 flex items-center gap-2.5 border-b border-border bg-card">
    <button class="size-10 rounded-xl grid place-items-center relative" style="background:var(--app-color)" title="Trocar de app"><i data-i="shopping-basket" class="size-5 text-white"></i></button>
    <p class="text-[18px] font-semibold">Encomendas</p>
    <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum"><span class="live-dot"></span>09:02</span>
    <div class="flex-1"></div>
    <button class="size-12 rounded-full grid place-items-center"><i data-i="search" class="size-5"></i></button>
    <button class="size-12 rounded-full grid place-items-center relative"><i data-i="bell" class="size-5"></i><span class="absolute top-1.5 right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[11px] font-bold grid place-items-center">2</span></button>
  </div>
  <div class="flex-1 min-h-0 overflow-hidden px-3 pt-3 flex flex-col gap-2.5">
    <label class="h-12 px-3 rounded-lg border border-input bg-card inline-flex items-center gap-2.5"><i data-i="search" class="size-5 text-muted-foreground"></i><span class="text-[15px] text-muted-foreground">Nome, telefone ou código</span></label>
    <div class="flex items-center gap-1.5 overflow-hidden fade-r">
      <button class="h-10 px-3.5 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-1.5 text-[14px] font-semibold shrink-0"><i data-i="check" class="size-4 text-primary"></i>Hoje <span class="tnum text-muted-foreground">4</span></button>
      <button class="h-10 px-3.5 rounded-full border border-border bg-card inline-flex items-center gap-1.5 text-[14px] shrink-0"><i data-i="store" class="size-4"></i>Retirada <span class="tnum text-muted-foreground">3</span></button>
      <button class="h-10 px-3.5 rounded-full border border-border bg-card inline-flex items-center gap-1.5 text-[14px] shrink-0"><i data-i="bike" class="size-4"></i>Entrega <span class="tnum text-muted-foreground">1</span></button>
      <button class="h-10 px-3.5 rounded-full border border-border bg-card inline-flex items-center gap-1.5 text-[14px] shrink-0">Amanhã <span class="tnum text-muted-foreground">6</span></button>
    </div>
    <p class="op-eyebrow text-muted-foreground pt-1">Sáb 04/10 · próximas primeiro</p>
    ${pcard({ time: "09:00", who: "Maria Santos", mode: "Retirada", mi: "store", items: "2× Croissant, 1× Pain au Chocolat", total: "R$ 41,00", s1: "success", l1: "Pronta", s2: "success", l2: "Paga", sel: 1 })}
    ${pcard({ time: "10:30", who: "Café Parisiense", mode: "Entrega", mi: "bike", items: "20× Croissant, 10× Baguette", total: "R$ 420,00", s1: "primary", l1: "Em preparo", s2: "warning", l2: "Pagar na entrega" })}
    ${pcard({ time: "11:00", who: "João Oliveira", mode: "Retirada", mi: "store", items: "1× Shokupan, 2× Madeleine", total: "R$ 41,00", s1: "info", l1: "Confirmada", s2: "warning", l2: "Pix aguardando" })}
    ${pcard({ time: "15:00", who: "Ana Ferreira", mode: "Retirada", mi: "store", items: "1× Brioche Nanterre", total: "R$ 22,00", s1: "info", l1: "Confirmada", s2: "muted", l2: "Pagar na retirada" })}
  </div>
  <!-- ação principal no polegar -->
  <div class="shrink-0 px-3 pt-2 pb-2 bg-background">
    <button class="w-full h-14 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[16px] font-semibold shadow-lg"><i data-i="scan-qr-code" class="size-6"></i>Ler código da encomenda</button>
  </div>
  <nav class="h-16 shrink-0 border-t border-border bg-card grid grid-cols-4">
    <a class="flex flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-muted-foreground relative"><i data-i="receipt" class="size-6"></i>Comandas<span class="absolute top-1.5 left-[54%] min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[11px] font-bold grid place-items-center">1</span></a>
    <a class="flex flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-primary relative"><span class="absolute top-0 inset-x-6 h-0.5 rounded-full bg-primary"></span><i data-i="calendar-clock" class="size-6"></i>Encomendas<span class="absolute top-1.5 left-[56%] min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[11px] font-bold grid place-items-center">4</span></a>
    <a class="flex flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-muted-foreground"><i data-i="wallet" class="size-6"></i>Caixa</a>
    <a class="flex flex-col items-center justify-center gap-0.5 text-[12px] font-semibold text-muted-foreground"><i data-i="ellipsis" class="size-6"></i>Mais</a>
  </nav>
  ${homeBar()}
</div>`;

const phoneB = `<div class="h-full flex flex-col cam text-white relative">
  ${statusBar(true)}
  <div class="h-14 shrink-0 px-3 flex items-center gap-2">
    <button class="size-12 rounded-full bg-white/15 grid place-items-center"><i data-i="x" class="size-6"></i></button>
    <p class="flex-1 text-center text-[16px] font-semibold">Ler código da encomenda</p>
    <button class="size-12 rounded-full bg-white grid place-items-center text-[#2a211b]" title="Lanterna ligada"><i data-i="flashlight" class="size-5"></i></button>
  </div>
  <!-- visor -->
  <div class="relative mx-auto mt-1 w-[208px] h-[208px]">
    <div class="absolute inset-3 rounded-lg bg-white grid place-items-center"><i data-i="qr-code" class="size-[150px] text-[#1b1410]"></i></div>
    <span class="scan-corner left-0 top-0 border-t-4 border-l-4 rounded-tl-xl"></span>
    <span class="scan-corner right-0 top-0 border-t-4 border-r-4 rounded-tr-xl"></span>
    <span class="scan-corner left-0 bottom-0 border-b-4 border-l-4 rounded-bl-xl"></span>
    <span class="scan-corner right-0 bottom-0 border-b-4 border-r-4 rounded-br-xl"></span>
    <span class="absolute -bottom-4 left-1/2 -translate-x-1/2 h-8 px-3 rounded-full bg-[#2f9e62] text-white text-[13px] font-semibold inline-flex items-center gap-1.5 shadow-lg whitespace-nowrap"><i data-i="vibrate" class="size-4"></i>Lido · vibrou</span>
  </div>
  <div class="mt-6 flex items-center justify-center gap-2">
    <button class="h-12 px-4 rounded-full bg-white/15 inline-flex items-center gap-2 text-[14px] font-semibold"><i data-i="keyboard" class="size-4"></i>Digite o código</button>
  </div>
  <!-- painel de baixo: a encomenda lida -->
  <div class="absolute inset-x-0 bottom-0 rounded-t-3xl bg-card text-foreground shadow-[0_-10px_30px_rgb(0_0_0/.35)] flex flex-col">
    <div class="pt-2.5 pb-1 grid place-items-center"><span class="w-10 h-1.5 rounded-full bg-border"></span></div>
    <div class="px-4 pt-0.5 pb-2.5 flex items-center gap-3 border-b border-border">
      <span class="size-11 rounded-full bg-secondary grid place-items-center text-[15px] font-semibold">MS</span>
      <div class="flex-1 min-w-0">
        <p class="text-[18px] leading-6 font-semibold">Maria Santos</p>
        <p class="text-[13px] leading-5 text-muted-foreground">Encomenda WEB-261004-K21 · (43) 99111-1111</p>
      </div>
    </div>
    <div class="px-4 py-2.5 flex flex-col gap-2">
      <div class="flex items-center gap-2 text-[14px]"><i data-i="store" class="size-4 text-muted-foreground"></i><span class="font-semibold">Retirada na loja</span><span class="text-muted-foreground">· sáb 04/10 às 09:00</span></div>
      <div class="flex items-center gap-1.5">${pill("success", "Pronta")}${pill("success", "Paga · Pix")}</div>
      <div class="rounded-lg bg-muted/60 px-3 py-1">
        <div class="h-9 flex items-center text-[15px]"><span class="w-8 font-semibold tnum">2×</span><span class="flex-1">Croissant Tradicional</span><span class="tnum">R$ 26,00</span></div>
        <div class="h-9 flex items-center text-[15px] border-t border-border"><span class="w-8 font-semibold tnum">1×</span><span class="flex-1">Pain au Chocolat</span><span class="tnum">R$ 15,00</span></div>
      </div>
      <div class="flex items-baseline"><span class="text-[13px] text-muted-foreground">Total</span><span class="ml-auto text-[22px] font-semibold tnum">R$ 41,00</span></div>
    </div>
    <div class="px-4 pt-1 pb-2 flex flex-col gap-2">
      <button class="w-full h-14 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[17px] font-semibold"><i data-i="hand-platter" class="size-6"></i>Entregar</button>
      <button class="w-full h-12 rounded-xl border border-border bg-card inline-flex items-center justify-center gap-2 text-[15px] font-semibold"><i data-i="receipt" class="size-5"></i>Abrir como comanda (acrescentar itens)</button>
    </div>
    ${homeBar()}
  </div>
</div>`;

const phone = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="900x1000">${STYLE}</head>
<body class="font-sans antialiased text-foreground" data-app="pos" style="background:#e9dfd6">
<div class="h-[1000px] relative flex justify-center gap-10 pt-5">
  <div class="flex flex-col items-center gap-3">
    <p class="op-title">Cliente veio buscar · lista de hoje</p>
    <div class="device"><div class="screen" style="width:390px;height:844px">${phoneA}</div></div>
  </div>
  <div class="flex flex-col items-center gap-3">
    <p class="op-title">Leitor aberto · leu o QR da mensagem</p>
    <div class="device"><div class="screen" style="width:390px;height:844px">${phoneB}</div></div>
  </div>
  <span class="pin" style="left:50px;top:100px">1</span>
  <span class="pin" style="left:50px;top:166px">2</span>
  <span class="pin" style="left:50px;top:320px">3</span>
  <span class="pin" style="left:404px;top:780px">4</span>
  <span class="pin" style="left:404px;top:846px">5</span>
  <span class="pin" style="left:836px;top:100px">6</span>
  <span class="pin" style="left:836px;top:560px">7</span>
  <span class="pin" style="left:836px;top:840px">8</span>
</div>
<div class="legend !grid-cols-2">
  <p class="t">PDV · celular <span>balcão de bolso: consulta e retirada de encomendas, comanda rápida na fila</span></p>
  <div><b>1</b>Barra de 56 px: selo do PDV (toque troca de app), título, ponto ao vivo, busca única em tela cheia e sino.</div>
  <div><b>2</b>Busca por nome, telefone ou código e chips roláveis (Hoje, Retirada, Entrega, Amanhã).</div>
  <div><b>3</b>Encomendas do dia em cards, a próxima primeiro, com hora, cliente, itens, total e as duas pílulas (preparo e pagamento). Toque abre o painel.</div>
  <div><b>4</b>Ação principal no polegar: "Ler código da encomenda" abre a câmera (QR da mensagem que a cliente recebeu).</div>
  <div><b>5</b>Barra inferior: Comandas (abrir comanda rápida para quem está na fila), Encomendas, Caixa e Mais (Terminal, Avisos, Bloquear).</div>
  <div><b>6</b>Leitor em tela cheia: lanterna, fechar e "Digite o código" quando o QR não lê. Ao ler, o dispositivo vibra.</div>
  <div><b>7</b>A encomenda lida sobe num painel de baixo: cliente, retirada, Pronta e Paga, itens e total, sem nenhuma tecla F.</div>
  <div><b>8</b>"Entregar" grande no alcance do polegar; "Abrir como comanda" quando a cliente quer acrescentar algo no balcão.</div>
</div>
</body></html>`;
W("pos-phone3", phone);
console.log("ok");
