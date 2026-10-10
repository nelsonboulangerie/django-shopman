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
    <span class="${name} font-semibold truncate${t.out ? " text-muted-foreground" : ""}">${t.n.replaceAll("&", "&amp;")}</span>
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
