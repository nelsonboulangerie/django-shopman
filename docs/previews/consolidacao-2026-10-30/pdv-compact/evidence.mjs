// PRÉVIA. Evidência A × C com Playwright headless (o chromium do node_modules do app).
// Uso: node evidence.mjs <pos-nuxt da cópia, para achar o playwright> <pasta de saída>
// Servidores: mock 38910, A 4301, C 4302 (run.sh). Medidas em evidence.json.
import {createRequire} from 'node:module';
import {writeFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
const [appDir,out]=process.argv.slice(2);
const {chromium}=createRequire(join(appDir,'package.json'))('playwright');
const MOCK='http://127.0.0.1:38910';
const VARIANTS={A:'http://127.0.0.1:4301',C:'http://127.0.0.1:4302'};
const VIEWPORTS=[[320,740],[320,568],[375,667],[390,844],[1440,900]];
await mkdir(join(out,'shots'),{recursive:true});
const evidence={generated_at:new Date().toISOString(),note:'Medidas em px CSS. firstContent = topo do 1º conteúdo útil da tela; headerBottom = fim da última faixa de cabeçalho visível; baseTop = topo do que flutua/fixa na base (barra de ação ou barra inferior).',screens:{},exercises:{},httpErrors:[]};
const reset=()=>fetch(MOCK+'/__preview/reset',{method:'POST'}).catch(()=>{});
const failNext=(body)=>fetch(MOCK+'/__preview/fail-next',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});

async function measure(page,first){
  return page.evaluate((first)=>{
    const vis=(e)=>{if(!e)return false;const r=e.getBoundingClientRect();const cs=getComputedStyle(e);return r.width>0&&r.height>0&&cs.visibility!=='hidden'&&cs.display!=='none';};
    const box=(e)=>{const r=e.getBoundingClientRect();return {top:Math.round(r.top),bottom:Math.round(r.bottom),height:Math.round(r.height)};};
    const vh=innerHeight;
    const headerSel='[data-compact-bar],[data-compact-active],[data-compact-settings-tabs],[data-operator-page-header],[data-page-header-filter-line],[data-page-header-active-filters],[data-page-header-filters-end],[data-page-header-alerts],[data-pos-sale-bar],[data-page-header-filters],[data-page-header-actions]';
    const header=[...document.querySelectorAll(headerSel)].filter(vis).filter(e=>e.getBoundingClientRect().top<vh/2);
    const headerBottom=Math.max(0,...header.map(e=>e.getBoundingClientRect().bottom));
    const bands=header.filter(e=>!header.some(o=>o!==e&&o.contains(e))).map(e=>({sel:[...e.attributes].map(a=>a.name).find(n=>n.startsWith('data-')),...box(e)}));
    const firstEl=first?[...document.querySelectorAll(first)].find(vis):null;
    const baseEls=[...document.querySelectorAll('[data-preorders-scan-bar],[data-preorder-hand-over-bar],[data-pos-sheet-bar],nav,[data-focus-obstruction]')].filter(vis).filter(e=>e.getBoundingClientRect().bottom>=vh-2&&e.getBoundingClientRect().top>vh/2);
    const baseTop=baseEls.length?Math.min(...baseEls.map(e=>e.getBoundingClientRect().top)):vh;
    const hdr=document.querySelector('[data-compact-header]');const useCompact=vis(hdr?.querySelector('[data-compact-bar]'));
    const scope=useCompact?hdr:document.querySelector('[data-operator-page-header]');
    const targets=scope?[...scope.querySelectorAll('button,a')].filter(vis).map(e=>({name:(e.getAttribute('aria-label')||e.textContent.trim()).slice(0,60),w:Math.round(e.getBoundingClientRect().width),h:Math.round(e.getBoundingClientRect().height)})):[];
    return {header:useCompact?'compacto':'kit',headerBottom:Math.round(headerBottom),bands,firstContent:firstEl?Math.round(firstEl.getBoundingClientRect().top):null,baseTop:Math.round(baseTop),usefulBetween:firstEl?Math.round(baseTop-firstEl.getBoundingClientRect().top):null,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,smallTargets:targets.filter(t=>t.w<44||t.h<44),targets};
  },first);
}
async function openSale(page,base){await page.goto(base+'/',{waitUntil:'networkidle'});await page.getByText('#12',{exact:true}).first().click();await page.locator('[data-pos-product]').first().waitFor();await page.waitForTimeout(700);}
async function openCheckout(page,base,wide){await openSale(page,base);
  if(wide){const b=page.locator('[data-pos-primary]:visible, [data-pos-ticket-column] button:has-text("Outras formas")').first();await b.click({timeout:8000});}
  else{await page.locator('[data-pos-sheet-bar] button').first().click();await page.waitForTimeout(700);await page.locator('[data-pos-sheet-other-payment]').click();}
  await page.waitForTimeout(1200);}
const SCREENS=[
  {key:'comandas',first:'[data-pos-tab-board-actions], input',go:(p,b)=>p.goto(b+'/',{waitUntil:'networkidle'})},
  {key:'venda',first:'[data-pos-product]',go:(p,b)=>openSale(p,b)},
  {key:'checkout',first:'[data-pos-payment-workspace], main [data-pos-work-column] > div:last-child',go:(p,b,w)=>openCheckout(p,b,w)},
  {key:'encomendas',first:'[data-preorder-card]',go:(p,b)=>p.goto(b+'/preorders',{waitUntil:'networkidle'})},
  {key:'encomenda-detalhe',first:'[data-preorder-counter-panel]',go:(p,b)=>p.goto(b+'/preorders/NB-1042',{waitUntil:'networkidle'})},
  {key:'caixa',first:'#shift-title',go:(p,b)=>p.goto(b+'/session',{waitUntil:'networkidle'})},
  {key:'ajustes-impressoras',first:'[data-pos-settings-shell] .max-w-4xl > *',go:(p,b)=>p.goto(b+'/settings/printers',{waitUntil:'networkidle'})},
  {key:'ajustes-salao',first:'[data-seating-screen] [data-compact-settings-tabs] ~ * , [data-seating-screen] main, [data-seating-screen] section',go:(p,b)=>p.goto(b+'/settings/seating',{waitUntil:'networkidle'})},
];
const browser=await chromium.launch();
async function newPage(w,h){const ctx=await browser.newContext({viewport:{width:w,height:h},hasTouch:w<1024,isMobile:w<1024,reducedMotion:'reduce',colorScheme:'light'});
  const page=await ctx.newPage();page.on('response',r=>{if(r.status()>=400&&!r.url().includes('/health/'))evidence.httpErrors.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);});return {ctx,page};}
const shot=(page,name,full=false)=>page.screenshot({path:join(out,'shots',name+'.png'),fullPage:full});

for(const [v,base] of Object.entries(VARIANTS)){
  for(const [w,h] of VIEWPORTS){
    await reset();const {ctx,page}=await newPage(w,h);
    for(const s of SCREENS){
      try{await s.go(page,base,w>=1024);await page.waitForTimeout(600);
        const m=await measure(page,s.first);(evidence.screens[s.key]??={})[`${v} ${w}x${h}`]=m;
        await shot(page,`${v}-${s.key}-${w}x${h}`);}
      catch(e){(evidence.screens[s.key]??={})[`${v} ${w}x${h}`]={error:String(e.message).slice(0,200)};}
    }
    await ctx.close();
  }
}

// Exercícios a 320×568 (o pior caso), iguais em A e C.
async function ex(v,name,fn){const {ctx,page}=await newPage(320,568);await reset();const log=[];
  try{await fn(page,VARIANTS[v],log,ctx);}catch(e){log.push('FALHOU: '+String(e.message).slice(0,200));}
  (evidence.exercises[name]??={})[v]=log;await ctx.close();}
const options=(v)=>v==='C'?'[data-compact-header] [data-compact-options]':'[data-operator-page-header] [data-page-header-more] button, [data-operator-page-header] button[aria-label^="Mais ações"]';
const inbox=(v)=>v==='C'?'[data-compact-header] [data-compact-inbox] button, [data-compact-header] [data-compact-bar] > :last-child button':'[data-page-header-inbox] button';
for(const v of ['A','C']){
  await ex(v,'encomendas: busca ativa e Limpar',async(p,b,log)=>{
    await p.goto(b+'/preorders',{waitUntil:'networkidle'});
    const btn=v==='C'?p.locator('[data-compact-header] button[aria-label^="Buscar"]'):p.locator('[data-page-header-search-toggle]');
    await btn.first().click();await p.waitForTimeout(600);await p.keyboard.type('Ana');await p.waitForTimeout(1200);await shot(p,`${v}-ex-busca-digitando`);
    await p.getByText(/Filtrar as encomendas por/).first().click();await p.waitForTimeout(1500);await shot(p,`${v}-ex-busca-ativa`);
    log.push('url com a busca: '+new URL(p.url()).search);
    log.push('faixa ativa: '+(await p.locator('[data-compact-active]').first().textContent().catch(()=>'(sem faixa compacta)')));
    log.push('1º resultado no topo: '+JSON.stringify(await measure(p,'[data-preorder-card]').then(m=>({headerBottom:m.headerBottom,firstContent:m.firstContent}))));
    if(v==='C'){await p.locator('[data-compact-active] button').click();await p.waitForTimeout(1000);log.push('após Limpar: url='+new URL(p.url()).search+' faixa='+(await p.locator('[data-compact-active]').count()));await shot(p,`${v}-ex-busca-limpa`);}
    else log.push('A: sem Limpar na linha; limpar é reabrir a busca e apagar o campo.');
  });
  await ex(v,'encomendas: filtro (recorte e período)',async(p,b,log)=>{
    await p.goto(b+'/preorders',{waitUntil:'networkidle'});
    if(v==='C'){await p.locator('[data-compact-header] button[aria-haspopup="dialog"][aria-label^="Filtros"]').click();await p.waitForTimeout(800);await shot(p,`${v}-ex-filtros-painel`);
      const chip=p.locator('[role=dialog] [data-compact-quick] button:visible').first();await chip.click();await p.waitForTimeout(600);const opt=p.locator('[role=option],[role=menuitemcheckbox],[role=menuitem]').filter({hasText:'A receber'}).first();log.push('recorte tocado: '+(await opt.innerText()).replace(/\s+/g,' '));await opt.click();await p.waitForTimeout(800);
      await shot(p,`${v}-ex-filtros-painel-com-recorte`);if(!(await p.getByRole('button',{name:'Ver resultados'}).isVisible()))await p.keyboard.press('Escape');await p.waitForTimeout(400);
      await p.getByRole('button',{name:'Ver resultados'}).click();await p.waitForTimeout(800);
      log.push('faixa ativa: '+(await p.locator('[data-compact-active]').textContent()));log.push('botão Filtros: '+(await p.locator('[data-compact-header] button[aria-label^="Filtros"]').getAttribute('aria-label')));
      await shot(p,`${v}-ex-filtro-ativo`);
      log.push('topo: '+JSON.stringify(await measure(p,'[data-preorder-card]').then(m=>({headerBottom:m.headerBottom,firstContent:m.firstContent}))));
    }else{const chip=p.locator('[data-preorders-quick] button:visible').first();await chip.click();await p.waitForTimeout(600);const opt=p.locator('[role=option],[role=menuitemcheckbox],[role=menuitem]').filter({hasText:'A receber'}).first();log.push('recorte tocado: '+(await opt.innerText()).replace(/\s+/g,' '));await opt.click();await p.waitForTimeout(600);await p.keyboard.press('Escape');await p.waitForTimeout(600);await shot(p,`${v}-ex-filtro-ativo`);
      log.push('topo: '+JSON.stringify(await measure(p,'[data-preorder-card]').then(m=>({headerBottom:m.headerBottom,firstContent:m.firstContent,bands:m.bands.length}))));}
  });
  await ex(v,'opções e avisos (Encomendas, Caixa)',async(p,b,log)=>{
    for(const r of ['/preorders','/session']){await p.goto(b+r,{waitUntil:'networkidle'});
      await p.locator(options(v)).first().click();await p.waitForTimeout(600);
      log.push(r+' ⋮: '+(await p.locator('[role=menu]').first().innerText()).replace(/\s+/g,' '));await shot(p,`${v}-ex-opcoes${r.replace(/\//g,'-')}`);await p.keyboard.press('Escape');await p.waitForTimeout(400);
      await p.locator(inbox(v)).first().click();await p.waitForTimeout(800);log.push(r+' avisos: '+((await p.locator('[role=dialog]').first().innerText().catch(()=>'(não abriu)')).replace(/\s+/g,' ').slice(0,140)));
      await shot(p,`${v}-ex-avisos${r.replace(/\//g,'-')}`);await p.keyboard.press('Escape');await p.waitForTimeout(400);}
  });
  await ex(v,'sem conexão',async(p,b,log,ctx)=>{
    await p.goto(b+'/preorders',{waitUntil:'networkidle'});await ctx.setOffline(true);await p.waitForTimeout(1500);
    log.push('selo: '+(await p.locator('[data-compact-seal]').first().getAttribute('aria-label').catch(()=>'(sem selo compacto)')));
    log.push('faixa offline visível: '+(await p.getByText(/sem conexão|offline/i).first().isVisible().catch(()=>false)));
    await shot(p,`${v}-ex-sem-conexao`);
    await openSale(p,b).catch(()=>{});await shot(p,`${v}-ex-sem-conexao-venda`);
    await ctx.setOffline(false);await p.waitForTimeout(1500);await shot(p,`${v}-ex-reconectou-venda`);
  });
  await ex(v,'erro de escrita e recuperação (Impressoras)',async(p,b,log)=>{
    await p.goto(b+'/settings/printers',{waitUntil:'networkidle'});
    await p.getByRole('radio',{name:'58 mm'}).first().click().catch(async()=>{await p.getByText('58 mm').first().click();});
    await failNext({});const save=p.getByRole('button',{name:'Gravar impressora'}).first();await save.click();await p.waitForTimeout(1200);
    log.push('após falha: '+((await p.locator('[data-sonner-toast], [role=alert]').allInnerTexts()).join(' | ').replace(/\s+/g,' ').slice(0,200)));await shot(p,`${v}-ex-erro-escrita`);
    await save.click();await p.waitForTimeout(1200);log.push('após repetir: '+((await p.locator('[data-sonner-toast], [role=status]').allInnerTexts()).join(' | ').replace(/\s+/g,' ').slice(0,200)));await shot(p,`${v}-ex-erro-recuperado`);
  });
  await ex(v,'venda: Não salvo continua visível',async(p,b,log)=>{
    await openSale(p,b);await failNext({method:'POST'});await failNext({method:'POST'});
    await p.locator('[data-pos-product]').nth(2).click();await p.waitForTimeout(500);
    const sel=v==='C'?'[data-compact-unsaved]':'[data-pos-unsaved]';log.push('selo Não salvo visível: '+(await p.locator(sel).first().isVisible().catch(()=>false)));
    await shot(p,`${v}-ex-venda-nao-salvo`);
  });
  await ex(v,'checkout e folha da comanda (maduros, só conferir)',async(p,b,log)=>{
    await openSale(p,b);await p.locator('[data-pos-sheet-bar] button').first().click();await p.waitForTimeout(800);await shot(p,`${v}-ex-folha-comanda`);
    await p.locator('[data-pos-sheet-other-payment]').click();await p.waitForTimeout(1200);await shot(p,`${v}-ex-checkout`);
    log.push('voltar: '+(await p.locator(v==='C'?'[data-compact-back]':'[data-pos-back]').first().getAttribute('aria-label').catch(()=>'?')));
  });
}
await browser.close();
await writeFile(join(out,'evidence.json'),JSON.stringify(evidence,null,1));
const s=evidence.screens;const pick=(k,vp)=>({A:s[k]?.[`A ${vp}`],C:s[k]?.[`C ${vp}`]});
for(const k of Object.keys(s))for(const vp of ['320x568','390x844']){const {A,C}=pick(k,vp);console.log(k,vp,'A',A?.firstContent??A?.error,'/',A?.usefulBetween,'C',C?.firstContent??C?.error,'/',C?.usefulBetween,'sw',A?.scrollWidth,C?.scrollWidth,'small',C?.smallTargets?.length);}
for(const [n,r] of Object.entries(evidence.exercises))console.log('#',n,JSON.stringify(r));
