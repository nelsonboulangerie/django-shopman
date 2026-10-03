// Gera src/pos-sale4.html e src/pos-tablet4.html
// usage: node gen-pos4.mjs && node build.mjs pos-sale4 pos-tablet4
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

const CHIPS = [
  ["Bebidas geladas", "#3E7FA8"], ["Bebidas quentes", "#8A5A3B"], ["Combos", "#7D4B88"], ["Doces", "#B8577A"],
  ["Folhados", "#C58A2B"], ["Macios", "#C9A56A"], ["Mercearia", "#5E7A4A"], ["Rústicos", "#8C6A3F"], ["Salgados", "#A95032"],
];
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

const STYLE4 = STYLE.replace("</style>", `
  .sw { width:30px; height:18px; border-radius:999px; background: color-mix(in oklab, var(--muted-foreground) 35%, transparent); position:relative; flex:none; }
  .sw::after { content:""; position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:999px; background: var(--card); box-shadow:0 1px 2px rgb(0 0 0/.25); }
  .inset { position:absolute; z-index:40; border:2px dashed #1f6feb; border-radius:14px; background: color-mix(in oklab, var(--background) 92%, transparent); box-shadow:0 10px 30px rgb(0 0 0/.18); }
  .inset > .tag { position:absolute; top:-12px; left:14px; background:#1f6feb; color:#fff; font:700 11px/16px "Instrument Sans",sans-serif; padding:2px 8px; border-radius:999px; white-space:nowrap; }
  .dim { position:absolute; inset:0; background: rgb(27 20 16 / .42); }
  .measure.r span { left:auto; right:8px; }
  .sw.sm { width:22px; height:13px; } .sw.sm::after { width:9px; height:9px; }
</style>`);

// ===================================================================
// 1) DESKTOP v4
// ===================================================================
// linhas: só qtd, nome, total. Secundário só quando existe (obs, desconto, cozinha).
const L4 = [
  { q: "2×", n: "Croissant Tradicional", t: "R$ 26,00" },
  { q: "1×", n: "Pain au Chocolat", t: "R$ 15,00" },
  { q: "2×", n: "Cappuccino", t: "R$ 28,00", obs: "1 sem açúcar", k: "21:52" },
  { q: "1×", n: "Baguette de Tradition", t: "R$ 16,00" },
  { q: "1×", n: "Caffè Latte", t: "R$ 14,00", k: "21:52" },
  { q: "1×", n: "Madeleine", t: "R$ 6,50" },
  { q: "1×", n: "Shokupan", t: "R$ 28,00" },
  { q: "1×", n: "Brioche Nanterre", t: "R$ 22,00" },
  { q: "1×", n: "Mini Focaccia Cebola", t: "R$ 12,00", send: 1 },
  { q: "1×", n: "Chausson aux Pommes", t: "R$ 14,40", disc: "R$ 16,00 − 10%", on: 1 },
  { q: "1×", n: "Chá Gelado Hibisco", t: "R$ 12,00" },
  { q: "1×", n: "Combo Café da Manhã (Grande)", t: "R$ 32,00", send: 1 },
  { q: "1×", n: "Limonada Siciliana", t: "R$ 11,00" },
];
const TOTAL4 = "R$ 236,90"; const ITEMS4 = 15; const TOSEND = 2;

const kFact = (time) => `<span class="inline-flex items-center gap-1 text-success"><i data-i="chef-hat" class="size-3.5"></i>na cozinha ${time}</span>`;
const sendFact = `<span class="inline-flex items-center gap-1 text-muted-foreground"><i data-i="chef-hat" class="size-3.5"></i>vai à cozinha</span>`;
function line4(l) {
  const subs = [];
  if (l.disc) subs.push(`<span class="inline-flex items-center gap-1 text-primary font-semibold"><i data-i="percent" class="size-3.5"></i>${l.disc}</span>`);
  if (l.obs) subs.push(`<span class="text-foreground/80">Obs.: ${l.obs}</span>`);
  if (l.k) subs.push(kFact(l.k));
  if (l.send) subs.push(sendFact);
  const sub = subs.length ? `<p class="op-micro text-muted-foreground tnum truncate flex items-center gap-2 mt-0.5">${subs.join('<span class="text-border">·</span>')}</p>` : "";
  const on = l.on ? " bg-primary/8 shadow-[inset_4px_0_0_var(--primary)]" : "";
  return `<li class="${subs.length ? "h-[58px]" : "h-12"} shrink-0 px-3.5 border-b border-border flex items-center gap-2.5${on}">
    <span class="op-title tnum w-8 shrink-0">${l.q}</span>
    <div class="flex-1 min-w-0"><p class="op-body ${l.on ? "font-semibold" : "font-medium"} truncate leading-5">${l.n}</p>${sub}</div>
    <span class="op-title tnum">${l.t}</span>
  </li>`;
}

const desktop4 = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="1440x900">${STYLE4}</head>
<body class="bg-background text-foreground font-sans antialiased" data-app="pos">
<div class="flex h-[900px] overflow-hidden relative">
  ${railDesktop}
  <main class="flex-1 flex flex-col min-w-0">
    <header class="h-14 shrink-0 px-3 flex items-center gap-2 border-b border-border bg-card">
      <button class="size-10 rounded-md border border-border bg-card grid place-items-center" title="Voltar às comandas (Esc)"><i data-i="arrow-left" class="size-5"></i></button>
      <div class="h-10 p-1 rounded-md bg-secondary inline-flex items-center gap-1" role="radiogroup">
        <button class="h-full px-2.5 rounded bg-card shadow-sm inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="store" class="size-4"></i>Balcão</button>
        <button class="h-full px-2.5 rounded inline-flex items-center gap-1.5 op-label text-muted-foreground"><i data-i="calendar-clock" class="size-4"></i>Encomendas</button>
      </div>
      <button class="h-10 px-2 rounded-md inline-flex items-center gap-1.5" title="Renomear comanda"><span class="op-figure !text-[22px]">Mesa 6</span><span class="op-micro text-muted-foreground tnum">#1007</span><i data-i="pencil" class="size-3.5 text-muted-foreground"></i></button>
      <div class="w-px h-6 bg-border"></div>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label" title="Cliente (F6)"><i data-i="user-round" class="size-4 text-muted-foreground"></i><span class="font-semibold">Maria Santos</span>${K("F6")}</button>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label" title="Recebimento (F7)"><i data-i="utensils" class="size-4 text-muted-foreground"></i><span class="font-semibold">Consumir aqui</span>${K("F7")}</button>
      <button class="h-10 pl-2.5 pr-2 rounded-full border border-dashed border-border bg-card inline-flex items-center gap-2 op-label text-muted-foreground" title="Quando (F8): agendar vira encomenda"><i data-i="calendar-clock" class="size-4"></i>Agora${K("F8")}</button>
      <div class="flex-1"></div>
      <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum px-1" title="Ao vivo · última leitura 22:03:14"><span class="live-dot"></span>22:03</span>
      <button class="size-10 rounded-md border border-border bg-card grid place-items-center" title="Últimas vendas"><i data-i="history" class="size-5"></i></button>
      <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label text-muted-foreground" title="Liberar comanda (pede confirmação)"><i data-i="x" class="size-4"></i>Liberar comanda</button>
    </header>

    <div class="flex-1 flex min-h-0">
      <section class="flex-1 min-w-0 flex flex-col relative">
        <div class="px-3 pt-2.5 pb-2 flex items-center gap-2">
          <label class="h-11 flex-1 px-3 rounded-md border-2 border-primary bg-card inline-flex items-center gap-2.5 shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_14%,transparent)]">
            <i data-i="search" class="size-5 text-muted-foreground"></i>
            <span class="flex-1 op-body text-muted-foreground truncate">Buscar produto, código, comanda ou cliente</span>
            <span class="op-micro text-muted-foreground">Enter adiciona</span>
            ${K("F3")}${K("/")}
          </label>
          <div class="h-11 p-1 rounded-md bg-secondary inline-flex items-center gap-1" role="radiogroup" title="Densidade da grade">
            <button class="h-full w-9 rounded grid place-items-center text-muted-foreground"><i data-i="grid-3x3" class="size-4"></i></button>
            <button class="h-full px-2 rounded bg-card shadow-sm inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="layout-grid" class="size-4"></i>Padrão</button>
            <button class="h-full w-9 rounded grid place-items-center text-muted-foreground"><i data-i="grid-2x2" class="size-4"></i></button>
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

      <!-- COMANDA: lista + total + Pagamento -->
      <aside class="w-[400px] shrink-0 border-l border-border bg-card flex flex-col relative">
        <div class="h-14 shrink-0 pl-3.5 pr-2.5 flex items-center gap-2 border-b border-border">
          <div class="min-w-0 leading-none">
            <p class="op-title tnum whitespace-nowrap">${ITEMS4} itens</p>
            <p class="mt-1 op-micro text-muted-foreground whitespace-nowrap">em ${L4.length} linhas</p>
          </div>
          <div class="flex-1"></div>
          <button class="h-10 px-2 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label shrink-0" title="Selecionar linhas (Alt S): Transferir, descontar, remover várias"><i data-i="list-checks" class="size-4"></i>${K("Alt S")}</button>
          <div class="flex flex-col items-stretch gap-0.5 shrink-0">
            <button class="h-9 pl-2.5 pr-1.5 rounded-md border border-primary bg-primary/8 inline-flex items-center gap-1.5 op-label font-semibold whitespace-nowrap" title="Enviar à cozinha as linhas novas (F9)"><i data-i="chef-hat" class="size-4 text-primary"></i>Enviar à cozinha<span class="min-w-5 h-5 px-1 rounded-full bg-primary text-primary-foreground text-[11px] grid place-items-center tnum">${TOSEND}</span>${K("F9")}</button>
            <span class="op-micro text-[11px] leading-3 text-muted-foreground inline-flex items-center justify-end gap-1 whitespace-nowrap" title="Envio automático por estação: decisão do dono, desligado por padrão"><span class="sw sm"></span>envio automático: desligado</span>
          </div>
        </div>
        <ul class="flex-1 min-h-0 overflow-hidden flex flex-col relative">
          ${L4.map(line4).join("\n")}
        </ul>

        <!-- editor da linha, sob demanda: cobre o pé da lista só enquanto a linha está tocada -->
        <div class="absolute left-0 right-0 bottom-[116px] h-[152px] z-10 bg-card border-t-2 border-primary shadow-[0_-10px_24px_rgb(0_0_0/.14)] px-3 pt-2 pb-2.5 flex flex-col justify-between">
          <div class="h-6 flex items-center gap-1.5 op-micro text-muted-foreground whitespace-nowrap"><i data-i="corner-left-up" class="size-3.5 text-primary"></i>Editando <b class="text-foreground font-semibold">Chausson aux Pommes</b> · R$ 16,00 cada</div>
          <div class="flex items-center gap-2">
            <div class="h-11 inline-flex items-center rounded-md border border-input bg-card overflow-hidden shrink-0" title="Quantidade: −/+ ou digite">
              <button class="size-11 grid place-items-center border-r border-border"><i data-i="minus" class="size-4"></i></button>
              <span class="w-11 text-center op-title tnum">1</span>
              <button class="size-11 grid place-items-center border-l border-border"><i data-i="plus" class="size-4"></i></button>
            </div>
            <button class="h-11 px-2.5 rounded-md inline-flex items-center gap-1.5 op-label font-semibold text-destructive whitespace-nowrap hover:bg-destructive/10" title="Remover, com desfazer"><i data-i="trash-2" class="size-4"></i>Remover${K("Del")}</button>
            <div class="flex-1"></div>
            <button class="h-11 px-2 rounded-md inline-flex items-center gap-1.5 op-label text-muted-foreground whitespace-nowrap" title="Fechar o editor">Fechar${K("Esc")}</button>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <button class="h-10 px-2.5 rounded-md border border-primary bg-primary/10 inline-flex items-center justify-center gap-1.5 op-label font-semibold whitespace-nowrap"><i data-i="percent" class="size-4 text-primary"></i>Desconto: 10%</button>
            <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center justify-center gap-1.5 op-label whitespace-nowrap"><i data-i="message-square-text" class="size-4"></i>Observação</button>
          </div>
        </div>

        <div class="h-7 shrink-0 px-3.5 flex items-center gap-2 border-t border-border bg-muted/50 op-micro text-muted-foreground whitespace-nowrap">
          <i data-i="keyboard" class="size-3.5"></i>Digite para mudar a quantidade <span class="text-border">·</span> Del remove <span class="text-border">·</span> ↑↓ troca a linha
        </div>
        <!-- pé: UMA faixa, o maior alvo da tela -->
        <div class="h-[88px] shrink-0 px-3 py-3 border-t border-border">
          <button class="h-16 w-full rounded-lg bg-primary text-primary-foreground pl-4 pr-3.5 flex items-center gap-3 shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]" title="Pagamento (F4)">
            <i data-i="credit-card" class="size-6"></i>
            <span class="text-[19px] font-semibold">Pagamento</span>${K("F4", "k-inv")}
            <span class="flex-1"></span>
            <span class="flex flex-col items-end leading-none"><span class="op-micro opacity-80">total</span><span class="text-[28px] leading-8 font-semibold tnum">${TOTAL4}</span></span>
          </button>
        </div>
      </aside>
    </div>
  </main>

  <!-- outro estado: modo seleção (só nele aparece Transferir) -->
  <div class="note" style="all:unset"><div class="inset" style="left:96px;top:640px;width:600px;padding:18px 14px 12px">
    <span class="tag">outro estado: modo seleção (Alt S) · o cabeçalho da comanda vira isto</span>
    <div class="rounded-lg border border-border bg-card overflow-hidden">
      <div class="h-14 px-3 flex items-center gap-2 border-b border-border bg-primary/8">
        <button class="size-9 rounded-md grid place-items-center" title="Sair (Esc)"><i data-i="x" class="size-4"></i></button>
        <p class="op-title tnum whitespace-nowrap">2 selecionadas</p>
        <div class="flex-1"></div>
        <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label font-semibold"><i data-i="split" class="size-4"></i>Transferir${K("F10")}</button>
        <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label"><i data-i="percent" class="size-4"></i>Desconto</button>
        <button class="h-10 px-2.5 rounded-md border border-border bg-card inline-flex items-center gap-1.5 op-label text-destructive"><i data-i="trash-2" class="size-4"></i>Remover</button>
      </div>
      <div class="h-10 px-3 flex items-center gap-2.5 border-b border-border"><span class="size-5 rounded bg-primary grid place-items-center"><i data-i="check" class="size-3.5 text-primary-foreground"></i></span><span class="op-title tnum w-7">2×</span><span class="op-body flex-1">Cappuccino</span><span class="op-title tnum">R$ 28,00</span></div>
      <div class="h-10 px-3 flex items-center gap-2.5"><span class="size-5 rounded bg-primary grid place-items-center"><i data-i="check" class="size-3.5 text-primary-foreground"></i></span><span class="op-title tnum w-7">1×</span><span class="op-body flex-1">Caffè Latte</span><span class="op-title tnum">R$ 14,00</span></div>
    </div>
  </div></div>

  <!-- medidas -->
  <div class="note" style="all:unset">
    <div class="measure r" style="left:1036px;top:112px;height:672px"><span style="top:24px;transform:none">lista, editor fechado: 672 px · 13 linhas</span></div>
    <div class="measure r" style="left:1022px;top:112px;height:520px"><span style="top:auto;bottom:10px;transform:none">editor aberto: 520 px · 10 linhas, a ativa por último</span></div>
  </div>

  <span class="pin" style="left:1117px;top:92px">1</span>
  <span class="pin" style="left:1290px;top:300px">2</span>
  <span class="pin" style="left:1044px;top:672px">3</span>
  <span class="pin" style="left:1326px;top:788px">4</span>
  <span class="pin" style="left:1044px;top:830px">5</span>
  <span class="pin" style="left:84px;top:628px">6</span>
  <span class="pin" style="left:510px;top:2px">7</span>
</div>
<div class="legend">
  <p class="t">PDV · Venda · v4 <span>desktop com teclado e leitor · COMPOSIÇÃO: a comanda é lista + total + Pagamento, e só</span></p>
  <div><b>1</b>Cabeçalho da comanda: contagem, Selecionar (Alt S) e Enviar à cozinha F9 com as linhas novas (2). Sob ele, o interruptor do envio automático por estação, desligado por padrão (decisão do dono, §5.1).</div>
  <div><b>2</b>Linha = qtd, nome, total. Preço unitário só com desconto ou peso. Fato na linha: "na cozinha 21:52" (enviada) ou "vai à cozinha" (falta enviar). Linha sem preparo não carrega nada.</div>
  <div><b>3</b>Clicar (ou ↑↓) numa linha abre o editor DELA, colado nela, por cima do pé da lista (152 px): −/+, Remover (Del, com desfazer), Desconto, Observação. Esc fecha e a lista volta inteira. Nenhum numérico na tela.</div>
  <div><b>4</b>O teclado físico edita a linha ativa: uma dica de 28 px no lugar do console de 204 px de hoje e da faixa de 44 px da v3.</div>
  <div><b>5</b>Pé de UMA faixa (88 px): Pagamento F4 com o total dentro, 376 × 64 px, o maior alvo da tela. Na v3 eram dois andares de botões em 112 px.</div>
  <div><b>6</b>Transferir (F10) só existe no modo seleção, onde as linhas já estão escolhidas; ali também Desconto e Remover em várias.</div>
  <div><b>7</b>Barra de contexto da v3 mantida: Balcão | Encomendas, Mesa 6 renomeável, Cliente F6, Recebimento F7, Quando F8, Últimas vendas, Liberar. Terminal, Caixa e Tela do cliente seguem no rail.</div>
  <div><b>=</b>Altura da lista: hoje 485 px (~8 linhas); v3 648 px (10 linhas, pé espremido); v4 672 px com o editor fechado (13 linhas: 8 de 48 px + 5 com fato de 58 px) e 520 px com ele aberto (10 linhas, a ativa colada nele).</div>
</div>
</body></html>`;
W("pos-sale4", desktop4);

// ===================================================================
// 2) TABLET v4 · em pé · segundo posto sem dinheiro físico
// ===================================================================
const T = Object.fromEntries([...TILES, ...EXTRA].map((t) => [t.sku, t]));
const FAV = ["CROISSANT", "PAIN-CHOCOLAT", "CAPPUCCINO", "CAFFE-LATTE", "BAGUETTE-TRADITION", "MADELEINE", "BRIOCHE-NANTERRE", "SHOKUPAN",
  "CHAUSSON-POMME", "MINI-FOCACCIA", "LIMONADA-SIC", "COMBO-CAFE", "BICHON-CITRON", "BAGUETE-GERGELIM", "PAIN-RAISINS", "CHA-HIBISCO"].map((k) => T[k]);

function tileT(t, count = 0) {
  const grpShadow = t.grp ? " shadow-[4px_4px_0_-1px_var(--card),4px_4px_0_0_var(--border)]" : "";
  return `<button ${t.out ? "disabled " : ""}class="rounded-xl border ${count ? "border-primary ring-2 ring-primary/30" : "border-border"} bg-card overflow-hidden text-left flex flex-col relative${grpShadow}">
  <div class="tile-fb h-[108px] grid place-items-center${t.out ? " opacity-55" : ""}" style="background:color-mix(in oklab,${t.c} 20%,var(--card))">
    <span style="color:${t.ink}" class="grid place-items-center"><i data-i="${t.i}" class="size-11"></i></span>
    ${t.grp ? `<span class="absolute z-10 left-2 top-2 h-7 px-2 rounded-full bg-card/90 op-micro font-semibold inline-flex items-center gap-1"><i data-i="layers" class="size-3.5"></i>${t.grp}</span>` : ""}
    ${count ? `<span class="absolute z-10 right-2 top-2 min-w-8 h-8 px-2 rounded-full bg-primary text-primary-foreground text-[15px] font-bold grid place-items-center tnum shadow">${count}</span>` : ""}
  </div>
  <div class="px-3 py-2.5 flex flex-col gap-0.5">
    <span class="op-body font-semibold truncate${t.out ? " text-muted-foreground" : ""}">${t.n.replace("&", "&amp;")}</span>
    ${t.out
      ? `<span class="flex items-center justify-between"><span class="op-title tnum text-muted-foreground">${t.p}</span><span class="h-6 px-2 rounded-full bg-muted text-muted-foreground op-micro font-semibold inline-flex items-center gap-1.5"><span class="size-1.5 rounded-full bg-muted-foreground"></span>Esgotado</span></span>`
      : `<span class="op-title tnum">${t.p.replace(" a ", "–")}</span>`}
  </div>
</button>`;
}

const tStatus = `<div class="h-6 shrink-0 px-5 flex items-center justify-between text-[13px] font-semibold bg-card">
  <span class="tnum">22:03</span><span class="inline-flex items-center gap-1.5"><i data-i="wifi" class="size-4"></i><span class="tnum">82%</span><i data-i="battery-full" class="size-5"></i></span>
</div>`;

const tTop = `<header class="h-16 shrink-0 px-3 flex items-center gap-2 border-b border-border bg-card">
  <button class="size-12 rounded-xl grid place-items-center relative" style="background:var(--app-color)" title="PDV: trocar de app"><i data-i="shopping-basket" class="size-6 text-white"></i><span class="absolute -bottom-1 -right-1 size-5 rounded-full bg-card grid place-items-center shadow"><i data-i="layout-grid" class="size-3"></i></span></button>
  <button class="size-12 rounded-lg grid place-items-center" title="Voltar às comandas"><i data-i="chevron-left" class="size-6"></i></button>
  <div class="leading-none mr-1"><p class="op-figure !text-[24px]">Mesa 6</p><p class="op-micro text-muted-foreground tnum mt-0.5">#1012 · aberta 21:48</p></div>
  <button class="h-12 px-3.5 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label font-semibold"><i data-i="utensils" class="size-4 text-muted-foreground"></i>Consumir aqui</button>
  <button class="h-12 px-3.5 rounded-full border border-dashed border-border bg-card inline-flex items-center gap-2 op-label text-muted-foreground"><i data-i="user-round-plus" class="size-4"></i>Cliente</button>
  <div class="flex-1"></div>
  <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum"><span class="live-dot"></span>22:03</span>
  <button class="size-12 rounded-full grid place-items-center relative" title="Avisos"><i data-i="bell" class="size-6"></i><span class="absolute top-1.5 right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[11px] font-bold grid place-items-center">2</span></button>
  <button class="size-12 rounded-full grid place-items-center" title="Juliana · tocar para trocar de operador ou bloquear"><span class="size-10 rounded-full bg-secondary grid place-items-center text-[14px] font-semibold">JO</span></button>
</header>`;

const tSearch = `<div class="px-4 pt-3 pb-2.5 flex items-center gap-2.5">
  <label class="h-14 flex-1 px-4 rounded-xl border border-input bg-card inline-flex items-center gap-3"><i data-i="search" class="size-6 text-muted-foreground"></i><span class="text-[17px] text-muted-foreground">Buscar produto ou comanda</span></label>
  <button class="h-14 px-4 rounded-xl border border-border bg-card inline-flex items-center gap-2 op-label font-semibold" title="Ler código de barras com a câmera"><i data-i="scan-barcode" class="size-6"></i>Ler código</button>
</div>
<div class="px-4 pb-3 flex items-center gap-2 overflow-hidden fade-r">
  <button class="h-12 px-4 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label font-semibold shrink-0"><i data-i="star" class="size-4 text-primary"></i>Favoritos</button>
  ${[["Bebidas quentes", "#8A5A3B"], ["Folhados", "#C58A2B"], ["Doces", "#B8577A"], ["Macios", "#C9A56A"], ["Rústicos", "#8C6A3F"], ["Salgados", "#A95032"], ["Bebidas geladas", "#3E7FA8"]]
    .map(([n, c]) => `<button class="h-12 px-4 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label shrink-0"><span class="size-2.5 rounded-full" style="background:${c}"></span>${n}</button>`).join("")}
</div>`;

const counts = (map) => FAV.map((t) => tileT(t, map[t.sku] || 0)).join("\n");
const tGrid = (map) => `<div class="flex-1 min-h-0 overflow-hidden px-4 grid grid-cols-4 auto-rows-max gap-3 content-start">${counts(map)}</div>`;

const tNav = `<nav class="h-[76px] shrink-0 pb-2 border-t border-border bg-card grid grid-cols-5 relative z-30">
  ${[["receipt", "Comandas", 1, "3"], ["calendar-clock", "Encomendas", 0, "4"], ["qr-code", "Retirada", 0, ""], ["clipboard-check", "Fim do dia", 0, ""], ["ellipsis", "Mais", 0, ""]]
    .map(([i, n, on, b]) => `<a class="flex flex-col items-center justify-center gap-1 relative ${on ? "text-primary font-semibold" : "text-muted-foreground"}">
      <span class="h-8 w-14 rounded-full grid place-items-center ${on ? "bg-primary/12" : ""}"><i data-i="${i}" class="size-6"></i></span><span class="text-[13px] leading-4">${n}</span>
      ${b ? `<span class="absolute top-1.5 left-[calc(50%+10px)] min-w-[18px] h-[18px] px-1 rounded-full ${on ? "bg-primary text-primary-foreground" : "bg-muted-foreground/80 text-white"} text-[11px] font-bold grid place-items-center">${b}</span>` : ""}
    </a>`).join("")}
</nav>`;

// ---- A: vendendo, folha recolhida
const sheetCollapsed = `<div class="shrink-0 relative z-20 -mt-3 rounded-t-2xl border-t border-x border-border bg-card shadow-[0_-12px_30px_rgb(0_0_0/.14)] px-4 pt-2 pb-3">
  <div class="mx-auto w-12 h-1.5 rounded-full bg-border mb-2"></div>
  <div class="flex items-center gap-3">
    <button class="flex-1 min-w-0 h-16 flex items-center gap-3 text-left" title="Tocar ou puxar para cima: ver as linhas">
      <span class="size-12 rounded-xl bg-secondary grid place-items-center relative"><i data-i="receipt" class="size-6"></i><span class="absolute -top-1.5 -right-1.5 min-w-6 h-6 px-1 rounded-full bg-primary text-primary-foreground text-[13px] font-bold grid place-items-center tnum">3</span></span>
      <span class="flex flex-col leading-none gap-1"><span class="text-[17px] font-semibold">3 itens <span class="text-muted-foreground font-normal">·</span> <span class="tnum">R$ 41,00</span></span>
        <span class="op-micro text-muted-foreground inline-flex items-center gap-1"><i data-i="chef-hat" class="size-3.5 text-success"></i><span class="text-success">2 na cozinha 22:01</span> · Croissant, Cappuccino, Caffè Latte</span></span>
      <i data-i="chevron-up" class="size-6 text-muted-foreground ml-auto"></i>
    </button>
    <button class="h-16 w-[250px] rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="credit-card" class="size-6"></i>Pagamento</button>
  </div>
</div>`;

const screenA = `<div class="h-full flex flex-col bg-background text-foreground">
  ${tStatus}${tTop}${tSearch}
  ${tGrid({ CROISSANT: 1, CAPPUCCINO: 1, "CAFFE-LATTE": 1 })}
  ${sheetCollapsed}
  ${tNav}
</div>`;

// ---- B: folha aberta, linha tocada, numérico sob demanda
const tLine = (q, n, t, sub = "", on = false) => `<li class="${sub ? "h-[68px]" : "h-16"} px-4 flex items-center gap-3 border-b border-border${on ? " bg-primary/8 shadow-[inset_4px_0_0_var(--primary)]" : ""}">
  <span class="text-[19px] font-semibold tnum w-9">${q}</span>
  <div class="flex-1 min-w-0"><p class="text-[17px] ${on ? "font-semibold" : "font-medium"} truncate leading-6">${n}</p>${sub ? `<p class="op-micro text-muted-foreground inline-flex items-center gap-2">${sub}</p>` : ""}</div>
  <span class="text-[19px] font-semibold tnum">${t}</span>
</li>`;
const nk = (t, cls = "bg-card border border-border text-[24px] font-semibold tnum") => `<button class="h-[64px] rounded-xl ${cls} grid place-items-center">${t}</button>`;

const sheetOpen = `<div class="absolute inset-x-0 bottom-[76px] top-[262px] z-20 rounded-t-2xl border-t border-x border-border bg-card shadow-[0_-16px_40px_rgb(0_0_0/.25)] flex flex-col">
  <div class="mx-auto w-12 h-1.5 rounded-full bg-border mt-2"></div>
  <div class="h-16 shrink-0 px-4 flex items-center gap-2 border-b border-border">
    <p class="text-[19px] font-semibold">Mesa 6 <span class="text-muted-foreground font-normal">·</span> <span class="tnum">4 itens</span></p>
    <div class="flex-1"></div>
    <button class="size-12 rounded-lg border border-border grid place-items-center" title="Selecionar linhas: Transferir, descontar, remover várias"><i data-i="list-checks" class="size-5"></i></button>
    <button class="h-12 px-4 rounded-lg border border-primary bg-primary/8 inline-flex items-center gap-2 op-label font-semibold"><i data-i="chef-hat" class="size-5 text-primary"></i>Enviar à cozinha<span class="min-w-6 h-6 px-1 rounded-full bg-primary text-primary-foreground text-[12px] grid place-items-center tnum">1</span></button>
    <button class="size-12 rounded-lg grid place-items-center" title="Recolher"><i data-i="chevron-down" class="size-6"></i></button>
  </div>
  <ul class="shrink-0">
    ${tLine("1×", "Croissant Tradicional", "R$ 13,00")}
    ${tLine("1×", "Caffè Latte", "R$ 14,00", `<span class="inline-flex items-center gap-1 text-success"><i data-i="chef-hat" class="size-3.5"></i>na cozinha 22:01</span>`)}
    ${tLine("2×", "Cappuccino", "R$ 28,00", `<span class="inline-flex items-center gap-1 text-success"><i data-i="chef-hat" class="size-3.5"></i>1 na cozinha 22:01</span><span class="text-border">·</span><span class="inline-flex items-center gap-1"><i data-i="chef-hat" class="size-3.5"></i>+1 vai à cozinha</span>`, true)}
  </ul>
  <!-- numérico sob demanda: só porque a linha foi tocada -->
  <div class="shrink-0 px-4 pt-3 pb-3 bg-primary/5 border-b border-border">
    <div class="flex items-center gap-3 mb-3">
      <span class="op-label text-muted-foreground">Quantidade de <b class="text-foreground">Cappuccino</b> (era 1)</span>
      <span class="ml-auto h-11 min-w-[88px] px-3 rounded-lg border-2 border-primary bg-card grid place-items-center text-[26px] font-semibold tnum">2</span>
    </div>
    <div class="grid grid-cols-[1fr_1fr_1fr_190px] gap-2">
      ${nk("1")}${nk("2")}${nk("3")}${nk(`<span class="inline-flex items-center gap-2 text-[16px]"><i data-i="percent" class="size-5"></i>Desconto</span>`, "bg-secondary border border-border font-semibold")}
      ${nk("4")}${nk("5")}${nk("6")}${nk(`<span class="inline-flex items-center gap-2 text-[16px]"><i data-i="message-square-text" class="size-5"></i>Observação</span>`, "bg-secondary border border-border font-semibold")}
      ${nk("7")}${nk("8")}${nk("9")}${nk(`<span class="inline-flex items-center gap-2 text-[16px]"><i data-i="trash-2" class="size-5"></i>Remover</span>`, "bg-card border border-destructive/40 text-destructive font-semibold")}
      ${nk(",")}${nk("0")}${nk(`<i data-i="delete" class="size-7"></i>`, "bg-card border border-border")}${nk(`<span class="inline-flex items-center gap-2 text-[17px]"><i data-i="check" class="size-5"></i>Pronto</span>`, "bg-foreground text-background font-semibold")}
    </div>
  </div>
  <div class="flex-1"></div>
  <!-- pé: só eletrônico -->
  <div class="shrink-0 px-4 pt-3 pb-4 flex flex-col gap-2.5">
    <div class="flex items-baseline gap-2"><span class="op-label text-muted-foreground">Pagar</span><span class="text-[30px] leading-9 font-semibold tnum">R$ 55,00</span><span class="ml-auto op-micro text-muted-foreground">neste dispositivo: só pagamento eletrônico</span></div>
    <div class="grid grid-cols-2 gap-3">
      <button class="h-16 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="qr-code" class="size-6"></i>PIX</button>
      <button class="h-16 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="credit-card" class="size-6"></i>Maquininha</button>
    </div>
    <button class="h-12 rounded-xl border border-dashed border-border inline-flex items-center justify-center gap-2 op-label"><i data-i="banknote" class="size-5 text-muted-foreground"></i><b class="font-semibold">Dinheiro: enviar ao caixa</b><span class="text-muted-foreground">(entra na fila do Balcão)</span></button>
  </div>
</div>`;

const screenB = `<div class="h-full flex flex-col bg-background text-foreground relative">
  ${tStatus}${tTop}${tSearch}
  ${tGrid({ CROISSANT: 1, CAPPUCCINO: 2, "CAFFE-LATTE": 1 })}
  <div class="h-[93px] shrink-0"></div>
  ${tNav}
  <div class="dim" style="bottom:76px;z-index:15"></div>
  ${sheetOpen}
</div>`;

const tablet4 = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="1792x1296">${STYLE4}</head>
<body class="font-sans antialiased" data-app="pos" style="background:#e9dfd6">
<div class="h-[1296px] relative px-6 pt-4 flex gap-10">
  <div class="flex flex-col gap-2.5">
    <p class="op-title text-[#3b2a1e]">a · Vendendo: a grade é a tela, a comanda é a folha de baixo</p>
    <div class="device tablet"><div class="screen" style="width:820px;height:1180px">${screenA}</div></div>
  </div>
  <div class="flex flex-col gap-2.5">
    <p class="op-title text-[#3b2a1e]">b · Folha aberta: tocou o Cappuccino, o numérico aparece só agora</p>
    <div class="device tablet"><div class="screen" style="width:820px;height:1180px">${screenB}</div></div>
  </div>

  <span class="pin" style="left:60px;top:84px">1</span>
  <span class="pin" style="left:700px;top:150px">2</span>
  <span class="pin" style="left:60px;top:520px">3</span>
  <span class="pin" style="left:576px;top:1086px">4</span>
  <span class="pin" style="left:60px;top:1200px">5</span>
  <span class="pin" style="left:1396px;top:352px">6</span>
  <span class="pin" style="left:1600px;top:622px">7</span>
  <span class="pin" style="left:1250px;top:994px">8</span>
</div>
<div class="legend">
  <p class="t">PDV · Venda · tablet em pé (820 × 1180) <span>um segundo posto, sem dinheiro físico: diferente do balcão de propósito (§10.2)</span></p>
  <div><b>1</b>Por que difere: o tablet não tem gaveta, bobina, leitor HID nem segundo monitor. Por isso não tem Caixa, Terminal nem Tela do cliente. O selo troca de app; o avatar troca operador ou bloqueia.</div>
  <div><b>2</b>Busca grande com "Ler código" pela câmera (mercearia, QR da encomenda). Coleções em chips de 48 px, Favoritos primeiro: o teclado virtual cobriria a grade, então tocar é o caminho principal.</div>
  <div><b>3</b>A grade é a tela: 4 colunas, 16 tiles de 188 px. O tile já na comanda mostra a contagem. Toque adiciona; pressão longa abre tamanho, observação e quantidade.</div>
  <div><b>4</b>Comanda como folha de baixo, sempre visível na zona do polegar: "3 itens · R$ 41,00", o fato da cozinha e Pagamento (250 × 64 px). Puxar para cima abre as linhas.</div>
  <div><b>5</b>Seções do trabalho do tablet embaixo: Comandas (mesa e fila longa), Encomendas, Retirada (ler o QR e entregar), Fim do dia (contar a vitrine andando).</div>
  <div><b>6</b>Folha aberta: linhas de 64 px com o fato da cozinha ("1 na cozinha 22:01 · +1 vai à cozinha"). Enviar à cozinha e Selecionar (Transferir mora lá) no cabeçalho da folha.</div>
  <div><b>7</b>O numérico só aparece porque a linha foi tocada: teclas de 64 px, Desconto, Observação, Remover e Pronto ao lado. Um instrumento só para a quantidade (sem −/+ duplicado).</div>
  <div><b>8</b>Pagar só eletrônico: PIX e Maquininha. "Dinheiro: enviar ao caixa" cria "receber R$ 55,00 · Mesa 6" na fila do Balcão; o mesmo vale para saldo de encomenda em dinheiro.</div>
</div>
</body></html>`;
W("pos-tablet4", tablet4);
