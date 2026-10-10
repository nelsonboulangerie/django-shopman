// Gera src/bi-sales3.html (barras desenhadas com divs, alturas calculadas aqui).
import fs from "node:fs";
const HERE = new URL(".", import.meta.url).pathname;

const days = ["05/09","06/09","07/09","08/09","09/09","10/09","11/09","12/09","13/09","14/09","15/09","16/09","17/09","18/09","19/09","20/09","21/09","22/09","23/09","24/09","25/09","26/09","27/09","28/09","29/09","30/09","01/10","02/10"];
const rev = [6.1,0,6.8,8.6,7.9,10.0,14.1,18.7,0,6.3,6.8,9.6,7.6,15.4,15.1,0,6.9,7.6,7.2,7.8,13.8,16.4,0,7.0,7.9,7.3,8.0,8.6];
const prev = [7.4,0,8.0,9.3,9.9,11.6,15.8,19.9,0,7.2,8.1,10.5,9.4,15.0,17.6,0,7.8,8.9,8.7,9.6,15.1,18.2,0,8.4,9.0,8.1,10.6,12.0];
const yooga = (i) => i < 8;
const max = 20;
const H = 128;
let bars = "";
rev.forEach((v, i) => {
  const h = Math.round((v / max) * H);
  const ph = Math.round((prev[i] / max) * H);
  const peak = v === 18.7;
  const closed = v === 0;
  bars += `<div class="relative flex-1 h-full flex items-end">
    ${closed ? `<div class="w-full h-[3px] rounded-sm bg-border"></div>` : `<div class="w-full rounded-t-[3px] ${yooga(i) ? "bg-[var(--chart-1)]/35" : "bg-[var(--chart-1)]"}" style="height:${h}px"></div>`}
    ${ph ? `<div class="absolute left-0 right-0 h-[2px] bg-foreground/55" style="bottom:${ph}px"></div>` : ""}
    ${peak ? `<span class="absolute left-1/2 -translate-x-1/2 op-micro font-semibold tnum whitespace-nowrap px-1.5 rounded bg-foreground text-background" style="bottom:${Math.max(h, ph) + 6}px">R$ 18,7 mil</span>` : ""}
  </div>`;
});
let ticks = "";
days.forEach((d, i) => {
  ticks += `<span class="flex-1 min-w-0 whitespace-nowrap text-center op-micro tnum ${i % 7 === 0 || i === 27 ? "text-muted-foreground" : "text-transparent"}">${d}</span>`;
});

// pedidos por hora (0..23)
const hours = [0,0,0,0,0,0,4,22,24,21,19,2447,18,16,0,0,0,0,0,9,0,6,0,0];
let hb = "", ht = "";
hours.forEach((v, i) => {
  const h = v ? Math.max(3, Math.round((v / 2447) * 120)) : 0;
  hb += `<div class="relative flex-1 h-full flex items-end">${h ? `<div class="w-full rounded-t-[2px] bg-[var(--chart-4)]" style="height:${h}px"></div>` : `<div class="w-full h-px bg-border"></div>`}${v === 2447 ? `<span class="absolute left-1/2 -translate-x-1/2 op-micro font-semibold tnum whitespace-nowrap" style="bottom:${h + 4}px">2.447</span>` : ""}</div>`;
  ht += `<span class="flex-1 min-w-0 whitespace-nowrap text-center op-micro tnum ${i % 4 === 0 ? "text-muted-foreground" : "text-transparent"}">${i}h</span>`;
});

// pedidos por dia da semana
const wk = [["seg",318],["ter",412],["qua",436],["qui",448],["sex",433],["sáb",559],["dom",0]];
let wb = "", wt = "";
wk.forEach(([l, v]) => {
  const h = v ? Math.round((v / 559) * 120) : 0;
  wb += `<div class="relative flex-1 h-full flex items-end px-1.5">${h ? `<div class="w-full rounded-t-[3px] ${v === 559 ? "bg-[var(--chart-3)]" : "bg-[var(--chart-3)]/70"}" style="height:${h}px"></div>` : `<div class="w-full h-px bg-border"></div>`}<span class="absolute left-1/2 -translate-x-1/2 op-micro tnum whitespace-nowrap ${v === 559 ? "font-semibold" : "text-muted-foreground"}" style="bottom:${h + 4}px">${v ? v.toLocaleString("pt-BR") : "fechado"}</span></div>`;
  wt += `<span class="flex-1 text-center op-micro text-muted-foreground">${l}</span>`;
});

const channels = [
  ["PDV", "store", "R$ 195.302,84", "2.532 pedidos", 93.6, "--chart-1"],
  ["WhatsApp", "message-circle", "R$ 7.265,00", "36 pedidos", 3.5, "--chart-2"],
  ["Loja online", "globe", "R$ 4.512,00", "24 pedidos", 2.2, "--chart-3"],
  ["iFood", "bike", "R$ 1.520,00", "14 pedidos", 0.7, "--chart-4"],
];
let ch = "";
channels.forEach(([n, ic, v, o, pct, c]) => {
  ch += `<div class="flex flex-col gap-1.5">
    <div class="flex items-center gap-2"><i data-i="${ic}" class="size-4 text-muted-foreground"></i><span class="op-label font-semibold">${n}</span><span class="op-micro text-muted-foreground tnum">${o}</span><span class="ml-auto op-label tnum font-semibold">${v}</span><span class="w-12 text-right op-micro tnum text-muted-foreground">${pct.toLocaleString("pt-BR")}%</span></div>
    <div class="h-2.5 rounded-full bg-muted overflow-hidden"><div class="h-full rounded-full bg-[var(${c})]" style="width:${Math.max(pct, 1.2)}%"></div></div>
  </div>`;
});

const prods = [
  ["Pain de Campagne", "2.021", "R$ 52.153,25", 25.0],
  ["Baguette de Tradition", "2.198", "R$ 41.092,52", 19.7],
  ["Croissant", "1.840", "R$ 23.920,00", 11.5],
  ["Pain au Chocolat", "1.212", "R$ 16.968,00", 8.1],
  ["Brioche", "640", "R$ 12.160,00", 5.8],
  ["Shokupan", "302", "R$ 9.966,00", 4.8],
];
let pr = "";
prods.forEach(([n, q, v, pct], i) => {
  pr += `<tr class="h-9 border-b border-border last:border-0">
    <td class="op-label font-semibold truncate max-w-0">${n}</td>
    <td class="op-label tnum text-right font-normal">${q}</td>
    <td class="op-label tnum text-right font-semibold">${v}</td>
    <td class="pl-3"><div class="h-1.5 rounded-full bg-muted overflow-hidden"><div class="h-full bg-[var(--chart-1)]" style="width:${pct * 4}%"></div></div></td>
  </tr>`;
});

const tpl = fs.readFileSync(`${HERE}/src-templates/bi-sales3.tpl.html`, "utf8");
const out = tpl
  .replace("%%BARS%%", bars).replace("%%TICKS%%", ticks)
  .replace("%%HBARS%%", hb).replace("%%HTICKS%%", ht)
  .replace("%%WBARS%%", wb).replace("%%WTICKS%%", wt)
  .replace("%%CHANNELS%%", ch).replace("%%PRODUCTS%%", pr);
fs.writeFileSync(`${HERE}/src/bi-sales3.html`, out);
console.log("ok");
