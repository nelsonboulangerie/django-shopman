// gera src/pos-tablet-fluxo4.html: storyboard de 4 telas do tablet (atender na mesa)
import fs from "node:fs";
const HERE = new URL(".", import.meta.url).pathname;

const status = (net = "wifi", bat = "82%", batIco = "battery-full") => `
<div class="h-6 shrink-0 px-5 flex items-center justify-between text-[13px] font-semibold bg-card">
  <span class="tnum">22:05</span><span class="inline-flex items-center gap-1.5">${net === "wifi" ? `<i data-i="wifi" class="size-4"></i>` : `<span class="text-[12px] font-bold">4G</span><i data-i="signal" class="size-4"></i>`}<span class="tnum">${bat}</span><i data-i="${batIco}" class="size-5"></i></span>
</div>`;

const header = (title, sub, extra = "") => `
<header class="h-16 shrink-0 px-3 flex items-center gap-2 border-b border-border bg-card">
  <button class="size-12 rounded-xl grid place-items-center relative" style="background:var(--app-color)"><i data-i="shopping-basket" class="size-6 text-white"></i><span class="absolute -bottom-1 -right-1 size-5 rounded-full bg-card grid place-items-center shadow"><i data-i="layout-grid" class="size-3"></i></span></button>
  ${sub ? `<button class="size-12 rounded-lg grid place-items-center"><i data-i="chevron-left" class="size-6"></i></button>` : ""}
  <div class="leading-none ml-1"><p class="op-figure !text-[24px]">${title}</p>${sub ? `<p class="op-micro text-muted-foreground tnum mt-0.5">${sub}</p>` : ""}</div>
  <div class="flex-1"></div>
  ${extra}
  <span class="inline-flex items-center gap-1.5 op-micro text-muted-foreground tnum"><span class="live-dot"></span>22:05</span>
  <button class="size-12 rounded-full grid place-items-center"><span class="size-10 rounded-full bg-secondary grid place-items-center text-[14px] font-semibold">JO</span></button>
</header>`;

const nav = (on = 0) => {
  const items = [["receipt", "Comandas", "3"], ["calendar-clock", "Encomendas", "4"], ["qr-code", "Retirada"], ["clipboard-check", "Fim do dia"], ["ellipsis", "Mais"]];
  return `<nav class="h-[72px] shrink-0 pb-1 border-t border-border bg-card grid grid-cols-5 relative z-30">${items.map(([ic, l, b], i) => `
  <a class="flex flex-col items-center justify-center gap-1 relative ${i === on ? "text-primary font-semibold" : "text-muted-foreground"}">
    <span class="h-8 w-14 rounded-full grid place-items-center ${i === on ? "bg-primary/12" : ""}"><i data-i="${ic}" class="size-6"></i></span><span class="text-[13px] leading-4">${l}</span>
    ${b ? `<span class="absolute top-1.5 left-[calc(50%+10px)] min-w-[18px] h-[18px] px-1 rounded-full ${i === on ? "bg-primary text-primary-foreground" : "bg-muted-foreground/80 text-white"} text-[11px] font-bold grid place-items-center">${b}</span>` : ""}
  </a>`).join("")}</nav>`;
};

const tile = (name, price, ic, col, fg, count = 0) => `
<button class="rounded-xl border ${count ? "border-primary ring-2 ring-primary/30" : "border-border"} bg-card overflow-hidden text-left flex flex-col relative">
  <div class="tile-fb h-[92px] grid place-items-center" style="background:color-mix(in oklab,${col} 20%,var(--card))">
    <span style="color:${fg}" class="grid place-items-center"><i data-i="${ic}" class="size-10"></i></span>
    ${count ? `<span class="absolute z-10 right-2 top-2 min-w-8 h-8 px-2 rounded-full bg-primary text-primary-foreground text-[15px] font-bold grid place-items-center tnum shadow">${count}</span>` : ""}
  </div>
  <div class="px-3 py-2 flex flex-col gap-0.5"><span class="op-body font-semibold truncate">${name}</span><span class="op-title tnum">${price}</span></div>
</button>`;

const F = "#C58A2B", Ff = "#9a6a1f", B = "#8A5A3B", Bf = "#6b4329", R = "#8C6A3F", Rf = "#6e5230", D = "#B8577A", Df = "#8e3d5b", G = "#3E7FA8", Gf = "#2d5f80";

// ---------- tela 1 ----------
const s1 = `<div class="h-full flex flex-col bg-background text-foreground relative">
${status()}
${header("Mesa 6", "#1012 · aberta 21:48", `<button class="h-11 px-3 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label font-semibold"><i data-i="utensils" class="size-4 text-muted-foreground"></i>Consumir aqui</button>`)}
<div class="px-4 pt-3 pb-2.5"><label class="h-14 px-4 rounded-xl border border-input bg-card flex items-center gap-3"><i data-i="search" class="size-6 text-muted-foreground"></i><span class="text-[17px] text-muted-foreground">Buscar produto</span><i data-i="scan-barcode" class="size-6 ml-auto text-muted-foreground"></i></label></div>
<div class="px-4 pb-3 flex items-center gap-2 overflow-hidden fade-r">
  <button class="h-12 px-4 rounded-full border border-primary bg-primary/10 inline-flex items-center gap-2 op-label font-semibold shrink-0"><i data-i="star" class="size-4 text-primary"></i>Favoritos</button>
  <button class="h-12 px-4 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label shrink-0"><span class="size-2.5 rounded-full" style="background:${B}"></span>Bebidas quentes</button>
  <button class="h-12 px-4 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label shrink-0"><span class="size-2.5 rounded-full" style="background:${F}"></span>Folhados</button>
  <button class="h-12 px-4 rounded-full border border-border bg-card inline-flex items-center gap-2 op-label shrink-0"><span class="size-2.5 rounded-full" style="background:${D}"></span>Doces</button>
</div>
<div class="flex-1 min-h-0 overflow-hidden px-4 grid grid-cols-3 auto-rows-max gap-3 content-start">
  ${tile("Croissant Tradicional", "R$ 13,00", "croissant", F, Ff, 1)}
  ${tile("Cappuccino", "R$ 14,00", "coffee", B, Bf, 2)}
  ${tile("Caffè Latte", "R$ 14,00", "coffee", B, Bf, 1)}
  ${tile("Pain au Chocolat", "R$ 15,00", "croissant", F, Ff)}
  ${tile("Baguette de Tradition", "R$ 16,00", "wheat", R, Rf)}
  ${tile("Madeleine", "R$ 6,50", "cake-slice", D, Df)}
  ${tile("Limonada Siciliana", "R$ 11,00", "cup-soda", G, Gf)}
  ${tile("Pain aux Raisins", "R$ 16,00", "croissant", F, Ff)}
  ${tile("Chá Gelado Hibisco", "R$ 12,00", "cup-soda", G, Gf)}
</div>
<div class="shrink-0 relative z-20 -mt-3 rounded-t-2xl border-t border-x border-border bg-card shadow-[0_-12px_30px_rgb(0_0_0/.14)] px-4 pt-2 pb-3">
  <div class="mx-auto w-12 h-1.5 rounded-full bg-border mb-2"></div>
  <div class="flex items-center gap-3 mb-2.5">
    <span class="size-12 rounded-xl bg-secondary grid place-items-center relative shrink-0"><i data-i="receipt" class="size-6"></i><span class="absolute -top-1.5 -right-1.5 min-w-6 h-6 px-1 rounded-full bg-primary text-primary-foreground text-[13px] font-bold grid place-items-center tnum">4</span></span>
    <span class="flex flex-col leading-none gap-1 min-w-0"><span class="text-[17px] font-semibold">4 itens <span class="text-muted-foreground font-normal">·</span> <span class="tnum">R$ 55,00</span></span>
      <span class="op-micro text-muted-foreground inline-flex items-center gap-1"><i data-i="chef-hat" class="size-3.5 text-primary"></i><span class="text-primary font-semibold">3 ainda não foram à cozinha</span></span></span>
    <i data-i="chevron-up" class="size-6 text-muted-foreground ml-auto"></i>
  </div>
  <div class="grid grid-cols-[1fr_168px] gap-3">
    <button class="h-16 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="chef-hat" class="size-6"></i>Enviar à cozinha <span class="min-w-7 h-7 px-1.5 rounded-full bg-primary-foreground/20 text-[15px] grid place-items-center tnum">3</span></button>
    <button class="h-16 rounded-xl border border-border bg-card inline-flex items-center justify-center gap-2 text-[17px] font-semibold"><i data-i="credit-card" class="size-5"></i>Pagamento</button>
  </div>
</div>
${nav(0)}
</div>`;

// ---------- cabeçalho do pagamento (telas 2 e 3) ----------
const payTop = (tab) => {
  const tabs = [["credit-card", "Cartão"], ["qr-code", "PIX"], ["banknote", "Dinheiro"]];
  return `
<div class="px-5 pt-4 pb-3 flex items-end justify-between">
  <div class="leading-none"><p class="op-label text-muted-foreground">Pagar · Mesa 6 · 4 itens</p><p class="text-[40px] leading-[46px] font-semibold tnum mt-1">R$ 55,00</p></div>
  <button class="h-11 px-3 rounded-full border border-dashed border-border inline-flex items-center gap-2 op-label text-muted-foreground"><i data-i="file-text" class="size-4"></i>CPF na nota</button>
</div>
<div class="mx-5 p-1 rounded-2xl bg-muted grid grid-cols-3 gap-1">
  ${tabs.map(([ic, l]) => `<button class="h-14 rounded-xl inline-flex items-center justify-center gap-2 text-[17px] ${l === tab ? "bg-card shadow font-semibold text-foreground" : "text-muted-foreground font-medium"}"><i data-i="${ic}" class="size-5"></i>${l}</button>`).join("")}
</div>`;
};

// ---------- tela 2: cartão ----------
const step = (n, t, sub) => `<li class="flex gap-3 items-start"><span class="size-8 shrink-0 rounded-full bg-secondary grid place-items-center text-[15px] font-bold tnum">${n}</span><span class="pt-1"><span class="text-[16px] font-semibold block leading-5">${t}</span>${sub ? `<span class="op-label text-muted-foreground">${sub}</span>` : ""}</span></li>`;
const s2 = `<div class="h-full flex flex-col bg-background text-foreground relative">
${status()}
${header("Pagamento", "Mesa 6 · #1012")}
${payTop("Cartão")}
<div class="px-5 pt-3 flex gap-2">
  <button class="h-12 px-5 rounded-full border-2 border-primary bg-primary/10 op-title inline-flex items-center gap-2"><i data-i="check" class="size-4 text-primary"></i>Crédito</button>
  <button class="h-12 px-5 rounded-full border border-border bg-card op-title font-medium">Débito</button>
</div>
<div class="mx-5 mt-4 rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
  <div class="flex items-center gap-4">
    <span class="size-16 rounded-2xl bg-primary/12 text-primary grid place-items-center shrink-0"><i data-i="smartphone-nfc" class="size-9"></i></span>
    <p class="text-[26px] leading-8 font-semibold">Passe <span class="tnum">R$ 55,00</span> na maquininha</p>
  </div>
  <ol class="flex flex-col gap-4">
    ${step(1, "Digite R$ 55,00 na maquininha, no crédito", "")}
    ${step(2, "O cliente aproxima ou insere o cartão", "a maquininha vai até a mesa com você")}
    ${step(3, "Aprovou na maquininha? Confirme aqui", "")}
  </ol>
</div>
<p class="mx-5 mt-4 op-label text-muted-foreground inline-flex gap-2"><i data-i="info" class="size-4 shrink-0 mt-px"></i><span>Nada vai para outra fila: o cliente paga sentado e a comanda fecha no turno do Balcão.</span></p>
<div class="flex-1"></div>
<div class="px-5 pb-5 flex flex-col gap-2.5">
  <button class="h-16 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="check" class="size-6"></i>Maquininha aprovou · Confirmar</button>
  <button class="h-12 rounded-xl border border-border bg-card inline-flex items-center justify-center gap-2 text-[16px] font-medium"><i data-i="rotate-ccw" class="size-5 text-muted-foreground"></i>Não passou</button>
</div>
</div>`;

// ---------- tela 3: dinheiro ----------
const chip = (l, on) => `<button class="h-14 rounded-xl ${on ? "border-2 border-primary bg-primary/10 font-semibold" : "border border-border bg-card font-medium"} text-[17px] tnum">${l}</button>`;
const s3 = `<div class="h-full flex flex-col bg-background text-foreground relative">
${status()}
${header("Pagamento", "Mesa 6 · #1012")}
${payTop("Dinheiro")}
<div class="px-5 pt-4">
  <p class="op-label text-muted-foreground mb-1.5">Recebi do cliente</p>
  <div class="h-16 px-4 rounded-xl border-2 border-primary bg-card flex items-center"><span class="text-[30px] font-semibold tnum">R$ 100,00</span></div>
  <div class="grid grid-cols-4 gap-2 mt-2.5">${chip("Exato", false)}${chip("R$ 60", false)}${chip("R$ 100", true)}<button class="h-14 rounded-xl border border-border bg-card text-[15px] font-medium inline-flex items-center justify-center gap-1.5"><i data-i="grid-3x3" class="size-4 text-muted-foreground"></i>Outro</button></div>
</div>
<div class="mx-5 mt-3 h-16 px-4 rounded-xl bg-success/12 flex items-center justify-between">
  <span class="text-[17px] font-semibold text-success inline-flex items-center gap-2"><i data-i="coins" class="size-6"></i>Troco</span><span class="text-[30px] font-semibold tnum text-success">R$ 45,00</span>
</div>
<div class="mx-5 mt-3 rounded-xl border border-border bg-card p-4 flex gap-3">
  <span class="size-11 rounded-xl bg-secondary grid place-items-center shrink-0"><i data-i="archive" class="size-6"></i></span>
  <div><p class="text-[16px] font-semibold leading-5">Entra na gaveta do Balcão (mesmo turno).</p><p class="op-body text-muted-foreground mt-0.5">Leve o dinheiro e traga o troco.</p></div>
</div>
<p class="mx-5 mt-2.5 op-label text-muted-foreground inline-flex gap-2"><i data-i="info" class="size-4 shrink-0 mt-px"></i><span>A comanda fecha agora. Até a gaveta, o dinheiro fica com você, como hoje fica com o garçom.</span></p>
<div class="flex-1"></div>
<div class="px-5 pb-5">
  <button class="w-full h-16 rounded-xl bg-primary text-primary-foreground inline-flex items-center justify-center gap-2.5 text-[19px] font-semibold shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"><i data-i="check" class="size-6"></i>Recebi <span class="tnum">R$ 100,00</span> · Confirmar</button>
</div>
</div>`;

// ---------- tela 4: sem energia ----------
const row = (kind, t, sub) => {
  const ico = { ok: ["circle-check", "text-success"], no: ["circle-x", "text-destructive"], attn: ["triangle-alert", "text-warning"] }[kind];
  return `<li class="py-3 flex gap-3 items-start border-t border-border first:border-t-0"><i data-i="${ico[0]}" class="size-6 shrink-0 ${ico[1]}"></i><span><span class="text-[16px] font-semibold block leading-5">${t}</span>${sub ? `<span class="op-label text-muted-foreground block mt-0.5">${sub}</span>` : ""}</span></li>`;
};
const s4 = `<div class="h-full flex flex-col bg-background text-foreground relative">
${status("4g", "64%", "battery-medium")}
${header("Comandas", "")}
<div class="px-4 py-3 bg-info/12 border-b border-info/25 flex items-center gap-3">
  <span class="size-10 rounded-full bg-info/15 text-info grid place-items-center shrink-0"><i data-i="wifi-off" class="size-5"></i></span>
  <p class="text-[15px] leading-5"><b class="font-semibold">Sem rede da loja</b> · vendendo pelo 4G deste dispositivo</p>
</div>
<div class="mx-4 mt-3 rounded-2xl border border-border bg-card px-4 pt-3 pb-1">
  <p class="op-title">O que funciona agora</p>
  <ul>
    ${row("ok", "Vender e lançar comandas", "")}
    ${row("ok", "Cartão pela maquininha", "ela tem bateria e 4G próprios")}
    ${row("ok", "PIX", "QR na tela, confirma sozinho")}
    ${row("ok", "Dinheiro: a gaveta abre na chave", "")}
    ${row("no", "Impressora e cupom", "sem recibo impresso; NFC-e com CPF sai normal")}
    ${row("attn", "Cozinha: só se os tablets dela tiverem bateria ou 4G", "se apagaram, avise a cozinha de voz")}
  </ul>
</div>
<div class="mx-4 mt-3 rounded-xl bg-muted px-4 py-3 flex gap-3">
  <i data-i="cloud-off" class="size-5 shrink-0 text-muted-foreground mt-0.5"></i>
  <p class="op-label text-muted-foreground">Sem internet nenhuma, o sistema não vende (não há modo offline hoje).<br><span class="italic">proposta: modo contingência é decisão à parte</span></p>
</div>
<div class="mx-4 mt-3 flex flex-col gap-2">
  <div class="h-14 px-4 rounded-xl border border-border bg-card flex items-center gap-3"><span class="op-title">Mesa 2</span><span class="op-label text-muted-foreground">3 itens</span><span class="ml-auto op-title tnum">R$ 38,00</span></div>
  <div class="h-14 px-4 rounded-xl border border-border bg-card flex items-center gap-3"><span class="op-title">Mesa 4</span><span class="op-label text-muted-foreground">2 itens</span><span class="ml-auto op-title tnum">R$ 27,00</span></div>
</div>
<div class="flex-1"></div>
${nav(0)}
</div>`;

// ---------- cartões de baixo ----------
const card = (title, body) => `<div class="w-[438px] rounded-2xl bg-white/70 border border-[#d8cabd] p-4 flex flex-col gap-2.5">${title}${body}</div>`;
const capT = (ic, t) => `<p class="text-[14px] font-semibold text-[#3b2a1e] inline-flex items-center gap-2"><i data-i="${ic}" class="size-4"></i>${t}</p>`;
const mini = (ic, l, s, tone) => `<div class="flex flex-col items-center gap-1 w-[76px] text-center"><span class="size-11 rounded-xl grid place-items-center ${tone}"><i data-i="${ic}" class="size-6"></i></span><span class="text-[12px] font-semibold leading-4">${l}</span><span class="text-[11px] leading-[14px] text-muted-foreground">${s}</span></div>`;
const qr = (() => { // QR estilizado (decorativo)
  let seed = 7, cells = "";
  const N = 21;
  const fin = (x, y) => (x < 7 && y < 7) || (x > 13 && y < 7) || (x < 7 && y > 13);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    let on;
    if (fin(x, y)) { const lx = x > 13 ? x - 14 : x, ly = y > 13 ? y - 14 : y; on = lx === 0 || ly === 0 || lx === 6 || ly === 6 || (lx >= 2 && lx <= 4 && ly >= 2 && ly <= 4); }
    else { seed = (seed * 9301 + 49297) % 233280; on = seed / 233280 > 0.52; }
    if (on) cells += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
  }
  return `<svg viewBox="-1 -1 23 23" class="size-[104px] shrink-0 bg-white rounded-lg" fill="#1b1410">${cells}</svg>`;
})();

const cards = [
  card(capT("receipt", "A comanda mora no servidor"), `<p class="text-[13px] leading-[18px] text-[#3b2a1e]">Aberta no tablet, ela aparece igual no Balcão. Fecha onde for mais perto: na mesa, pelo tablet, ou no caixa, se o cliente levantar para pagar.</p>
    <div class="flex items-center gap-2 mt-1"><span class="h-8 px-3 rounded-full bg-card border border-border text-[12px] font-semibold inline-flex items-center gap-1.5"><i data-i="tablet" class="size-4"></i>Tablet</span><i data-i="arrow-left-right" class="size-4 text-muted-foreground"></i><span class="h-8 px-3 rounded-full bg-card border border-border text-[12px] font-semibold inline-flex items-center gap-1.5"><i data-i="cloud" class="size-4"></i>Mesa 6</span><i data-i="arrow-left-right" class="size-4 text-muted-foreground"></i><span class="h-8 px-3 rounded-full bg-card border border-border text-[12px] font-semibold inline-flex items-center gap-1.5"><i data-i="monitor" class="size-4"></i>Balcão</span></div>`),
  card(capT("qr-code", "Aba PIX: o cliente lê o QR na tela do tablet"), `<div class="flex gap-4 items-center">${qr}<div class="flex flex-col gap-1.5"><span class="text-[22px] font-semibold tnum leading-7">R$ 55,00</span><span class="h-7 px-2.5 rounded-full pill-info text-[12px] font-semibold inline-flex items-center gap-1.5 self-start"><span class="size-2 rounded-full bg-info"></span>Aguardando o pagamento</span><span class="text-[12px] leading-4 text-muted-foreground">Vire a tela para o cliente. Quando o PIX cai, a comanda fecha sozinha: nenhum botão a tocar.</span></div></div>`),
  card(capT("archive", "Uma gaveta, um turno, um fechamento"), `<div class="flex items-center justify-between px-1">
    ${mini("tablet", "Tablet", "posto 2", "bg-card border border-border")}
    <i data-i="arrow-right" class="size-5 text-muted-foreground"></i>
    ${mini("archive", "Gaveta do Balcão", "turno aberto", "bg-primary/12 text-primary")}
    <i data-i="arrow-left" class="size-5 text-muted-foreground"></i>
    ${mini("monitor", "Balcão", "posto 1", "bg-card border border-border")}
  </div><p class="text-[12px] leading-4 text-muted-foreground">O tablet é provisionado para compartilhar o terminal do Balcão: o dinheiro da mesa entra no mesmo turno e na mesma contagem cega.</p>`),
  card(capT("zap-off", "Sem energia: quem segue de pé"), `<div class="flex items-start justify-between">
    ${mini("router", "Roteador", "apagou", "pill-destructive")}
    ${mini("tablet", "Tablet", "bateria + 4G", "pill-success")}
    ${mini("credit-card", "Maquininha", "bateria + 4G", "pill-success")}
    ${mini("printer", "Impressora", "apagou", "pill-destructive")}
    ${mini("key-round", "Gaveta", "abre na chave", "pill-warning")}
  </div>`),
].join("");

const frame = (n, cap, screen) => `
<div class="flex flex-col gap-2 w-[438px]">
  <p class="h-[44px] flex items-start gap-2.5 text-[#3b2a1e]"><span class="size-7 shrink-0 rounded-full bg-[#3b2a1e] text-white grid place-items-center text-[14px] font-bold">${n}</span><span class="text-[16px] leading-[22px] font-semibold pt-0.5">${cap}</span></p>
  <div class="fr"><div class="fr-screen"><div class="fr-inner">${screen}</div></div></div>
</div>`;

const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport-size" content="1840x930"><style>
  .tile-fb { position:relative; overflow:hidden; }
  .tile-fb::after { content:""; position:absolute; inset:0; background:radial-gradient(circle at 85% 15%, rgb(255 255 255 / .35), transparent 55%); }
  .fade-r { -webkit-mask-image: linear-gradient(90deg, #000 88%, transparent); mask-image: linear-gradient(90deg, #000 88%, transparent); }
  .fr { width:438px; height:618px; padding:9px; border-radius:22px; background:#1b1410; box-shadow:0 16px 40px rgb(0 0 0/.3), inset 0 0 0 2px #3a2c22; }
  .fr-screen { width:420px; height:600px; border-radius:11px; overflow:hidden; position:relative; }
  .fr-inner { width:600px; height:857px; transform:scale(.7); transform-origin:0 0; }
</style></head>
<body class="font-sans antialiased" data-app="pos" style="background:#e9dfd6">
<div class="h-[930px] relative px-4 pt-4">
  <div class="flex justify-between">
    ${frame(1, "Na mesa: abre a comanda e lança", s1)}
    ${frame(2, "Cartão: a maquininha vai até a mesa", s2)}
    ${frame(3, "Dinheiro: recebe na mesa, troco da mesma gaveta", s3)}
    ${frame(4, "Sem energia: o tablet segue no 4G", s4)}
  </div>
  <div class="flex justify-between mt-5">${cards}</div>
  __PINS__
</div>
<div class="legend">
  <p class="t">PDV · Tablet na mesa · storyboard (4 telas em pé, 600 × 857 reduzidas a 70%) <span>proposta: o tablet é um segundo posto que COMPARTILHA a gaveta e o turno do Balcão; todo meio de pagamento na mesa</span></p>
  __LEG__
</div>
</body></html>`;

const pins = [
  [1330, 724, 1], [290, 522, 2], [848, 328, 3], [860, 722, 4], [1305, 446, 5], [1310, 250, 6], [1772, 149, 7], [1772, 490, 8],
];
const leg = [
  "Gaveta compartilhada: o tablet é provisionado para usar o mesmo terminal do Balcão (\"todos usam a mesma gaveta e o mesmo turno\"). Venda na mesa fecha no turno aberto do Balcão e entra na mesma contagem cega do fim do dia.",
  "A comanda mora no servidor: abre no tablet, lança, envia à cozinha (uma ação primária). Fecha no tablet ou no Balcão, sem transferir nada.",
  "Cartão igual ao balcão: sem fio até a maquininha hoje. O atendente leva a maquininha (bateria e 4G próprios), digita o valor e confirma no PDV. Integração Stone (TEF) é futuro.",
  "PIX: QR dinâmico na própria tela, virada para o cliente. O status muda sozinho quando o PIX cai (o sistema fez); não há botão de confirmar.",
  "Dinheiro sem fila: substitui o antigo \"enviar ao caixa\", que fazia o cliente pagar de novo no Balcão. O atendente recebe, a comanda fecha, e ele leva o dinheiro à gaveta e traz o troco, como o garçom faz hoje.",
  "Valor recebido por atalhos (Exato, R$ 60, R$ 100); o numérico só abre em \"Outro\". O troco aparece calculado antes do gesto de confirmar.",
  "Sem energia: o roteador apaga, o tablet segue na bateria e no 4G (ou hotspot). Impressora e abertura automática da gaveta param; NFC-e com CPF continua saindo pelo servidor.",
  "O limite honesto: tudo depende do servidor na nuvem. Sem internet nenhuma, não há venda (não existe fila offline). Modo contingência é decisão de produto à parte.",
];
const out = html.replace("__PINS__", pins.map(([x, y, n]) => `<span class="pin" style="left:${x}px;top:${y}px">${n}</span>`).join("")).replace("__LEG__", leg.map((t, i) => `<div><b>${i + 1}</b><span>${t}</span></div>`).join("\n  "));
fs.writeFileSync(`${HERE}src/pos-tablet-fluxo4.html`, out);
console.log("ok");
