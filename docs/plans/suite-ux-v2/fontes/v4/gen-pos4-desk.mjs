
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
