
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
