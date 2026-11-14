// PRÉVIA. Evidência A × C do Receber compacto (Playwright headless, chromium do cache).
// Uso: node evidence.mjs <playwright/index.mjs> <pasta de saída>. Mock 38930, A 4321, C 4322.
// O mock tem UM cenário global: A e C rodam em sequência, nunca ao mesmo tempo.
import {writeFile} from 'node:fs/promises';
const [pwPath,out]=process.argv.slice(2);
const {chromium}=await import(pwPath);
const MOCK='http://127.0.0.1:38930',PORT={A:4321,C:4322};
const VIEWPORTS=[[320,740],[320,568],[375,667],[390,844],[1440,900]];
const scenario=(s)=>fetch(`${MOCK}/__visual/scenario?set=${s}`);
const ev={generatedAt:new Date().toISOString(),notes:[],runs:{}};
const b=await chromium.launch();

async function measure(p){return p.evaluate(()=>{
  const vis=(e)=>{if(!e)return null;const r=e.getBoundingClientRect();const cs=getComputedStyle(e);return r.width>0&&r.height>0&&cs.visibility!=='hidden'?r:null;};
  const q=(s)=>[...document.querySelectorAll(s)].map(vis).find(Boolean)||null;
  const main=q('main[data-compact-page],main');const scroll=q('[data-receive-scroll]')||q('[data-operator-content-panel] section');
  const useful=q('[data-exception-progress]')||q('[data-receipt-in-progress]')||q('[data-receipt-type-key]')||q('[data-receipt-key-entry]')||q('[data-purchase-load-error]');
  const thumb=q('[data-receipt-thumb]'),tabs=q('[data-operator-suite-tabs]');
  const footTop=thumb?.top??tabs?.top??innerHeight;
  const hdrSel=document.querySelector('[data-compact-bar]')&&vis(document.querySelector('[data-compact-bar]'))?'[data-compact-header] button, [data-compact-header] a':'[data-operator-page-header-landmark] button, [data-operator-page-header-landmark] a, [data-operator-page-header-landmark] [role=combobox]';
  const targets=[...document.querySelectorAll(hdrSel)].map(e=>({e,r:vis(e)})).filter(x=>x.r&&x.r.top<200).map(({e,r})=>({name:(e.getAttribute('aria-label')||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,60),w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.left)}));
  const bell=q('[data-operator-inbox-trigger][data-placement=header]');
  return {vw:innerWidth,vh:innerHeight,headerHeight:scroll&&main?Math.round(scroll.top-main.top):null,contentTop:scroll?Math.round(scroll.top):null,
    firstUsefulTop:useful?Math.round(useful.top):null,actionBarTop:thumb?Math.round(thumb.top):null,actionBarHeight:thumb?Math.round(thumb.height):null,
    quickBarTop:tabs?Math.round(tabs.top):null,quickBarHeight:tabs?Math.round(tabs.height):null,
    listUsefulHeight:scroll?Math.round(footTop-scroll.top):null,scrollClientHeight:scroll?Math.round(scroll.height):null,
    scrollWidth:document.documentElement.scrollWidth,horizontalOverflow:document.documentElement.scrollWidth>innerWidth,
    headerTargets:targets,under44:targets.filter(t=>t.w<44||t.h<44).map(t=>`${t.name} ${t.w}x${t.h}`),
    bell:bell?{x:Math.round(bell.left),y:Math.round(bell.top)}:null,
    liveStatus:Boolean(q('[data-operator-live-status]')||q('[data-live-status]')),rail:Boolean(q('[data-suite-rail]')),
    offlineBand:Boolean(q('[data-operator-offline-band]')||q('[data-operator-offline-banner]')),
    h1:[...document.querySelectorAll('h1')].map(h=>h.textContent.trim()).filter(Boolean)};
});}

async function page(v,w,h){const ctx=await b.newContext({viewport:{width:w,height:h},hasTouch:w<768,isMobile:w<768,deviceScaleFactor:1,bypassCSP:true});const p=await ctx.newPage();p.setDefaultTimeout(10000);p.base=`http://127.0.0.1:${PORT[v]}`;return {ctx,p};}
async function go(p,path){await p.goto(p.base+path);await p.waitForLoadState('networkidle').catch(()=>{});await p.waitForTimeout(900);}
const shot=(p,name)=>p.screenshot({path:`${out}/${name}.png`});
async function closeAll(p){await p.keyboard.press('Escape');await p.waitForTimeout(350);}

for(const v of ['A','C']){
  const R=ev.runs[v]={};
  // 1. Matriz: começo e conferência em cada largura.
  for(const [w,h] of VIEWPORTS){
    const {ctx,p}=await page(v,w,h);const k=`${w}x${h}`;
    await scenario('normal');await go(p,'/receive');await shot(p,`${v}-${k}-1-comeco`);R[`${k}/comeco`]=await measure(p);
    await scenario('receiving');await go(p,'/receive');await shot(p,`${v}-${k}-2-conferencia`);R[`${k}/conferencia`]=await measure(p);
    await ctx.close();
  }
  // 2. Exercícios no celular de pouca altura e no comum.
  for(const [w,h] of [[320,568],[375,667]]){
    const k=`${w}x${h}`;const {ctx,p}=await page(v,w,h);
    // Busca no começo (a da suíte): abre e fecha sem mudar a tela.
    try{await scenario('normal');await go(p,'/receive');
      await (v==='C'?p.locator('[data-compact-bar] button[aria-label^="Buscar"]'):p.locator('[data-page-header-search-toggle]')).first().click();
      await p.waitForTimeout(500);await shot(p,`${v}-${k}-2b-comeco-busca`);R[`${k}/comeco-busca-abriu`]=await p.locator('[data-suite-search-panel], [role=dialog]').first().isVisible();await closeAll(p);
    }catch(e){R[`${k}/comeco-busca-erro`]=String(e).slice(0,300);await closeAll(p);}
    await scenario('receiving');await go(p,'/receive');
    // Busca + Limpar
    try{
      const btn=v==='C'?p.locator('[data-compact-bar] button[aria-label^="Buscar"]'):p.locator('[data-page-header-search-toggle]');
      await btn.first().click();await p.waitForTimeout(500);
      await p.keyboard.type('manteiga');await p.waitForTimeout(500);await shot(p,`${v}-${k}-3-busca-painel`);
      await p.locator('[data-suite-search-screen=apply]').first().click();await p.waitForTimeout(600);
      await shot(p,`${v}-${k}-4-busca-ativa`);R[`${k}/busca-ativa`]=await measure(p);
      R[`${k}/busca-ativa`].visibleIndicator=await p.evaluate(()=>{const a=document.querySelector('[data-compact-active]');if(a&&a.getBoundingClientRect().height)return a.innerText.replace(/\s+/g,' ');const list=document.querySelector('[data-receipt-list]');return {listVisible:Boolean(list&&list.getBoundingClientRect().height),bodyHasTerm:document.body.innerText.toLowerCase().includes('com “manteiga”')};});
      if(v==='C'){await p.locator('[data-compact-active] button',{hasText:'Limpar'}).click();}
      else{await p.locator('[data-page-header-search-toggle]').first().click();await p.waitForTimeout(400);await p.locator('[data-suite-search-screen=clear]').first().click();}
      await p.waitForTimeout(400);await shot(p,`${v}-${k}-5-busca-limpa`);R[`${k}/busca-limpa`]=await measure(p);
    }catch(e){R[`${k}/busca-erro`]=String(e).slice(0,300);await closeAll(p);}
    // Opções
    try{
      await (v==='C'?p.locator('[data-compact-options]'):p.locator('[data-page-header-more] button, button[data-page-header-more]')).first().click();
      await p.waitForTimeout(500);await shot(p,`${v}-${k}-6-opcoes`);
      R[`${k}/opcoes`]=await p.evaluate(()=>[...document.querySelectorAll('[role=menu] [role=menuitem], [role=menu] [data-slot=label]')].map(e=>e.textContent.trim().replace(/\s+/g,' ')));
      await closeAll(p);
    }catch(e){R[`${k}/opcoes-erro`]=String(e).slice(0,300);await closeAll(p);}
    // Menu completo (gaveta: seções, operador, atalhos)
    try{
      if(v==='C'){await p.locator('[data-compact-options]').click();await p.waitForTimeout(400);await p.getByRole('menuitem',{name:/Menu completo/}).click();}
      else{await p.locator('[data-operator-page-header] button[aria-label*="menu" i], [data-operator-page-header] button[aria-label*="barra lateral" i]').first().click();}
      await p.waitForTimeout(800);await shot(p,`${v}-${k}-7-gaveta`);
      R[`${k}/gaveta`]=await p.evaluate(()=>{const d=document.querySelector('[role=dialog]');return d?d.innerText.replace(/\s+/g,' ').slice(0,200):'(nenhuma gaveta aberta)';});
      await closeAll(p);
    }catch(e){R[`${k}/gaveta-erro`]=String(e).slice(0,300);await closeAll(p);}
    // Avisos
    try{
      await p.locator('[data-operator-inbox-trigger][data-placement=header]').filter({visible:true}).first().click();
      await p.waitForTimeout(500);await shot(p,`${v}-${k}-8-avisos`);await closeAll(p);
    }catch(e){R[`${k}/avisos-erro`]=String(e).slice(0,300);await closeAll(p);}
    // Item aberto (folha) pelo endereço ?line=
    try{
      const id=await p.locator('[data-receipt-line]').first().getAttribute('data-receipt-line');
      await go(p,`/receive?line=${id}`);await shot(p,`${v}-${k}-9-item-folha`);R[`${k}/item-folha`]=await measure(p);await closeAll(p);
    }catch(e){R[`${k}/item-erro`]=String(e).slice(0,300);}
    // Erro de escrita (contagem de volumes 500 uma vez) e a recuperação
    try{
      await go(p,'/receive');let failed=false;
      await p.route('**/receipts/volumes/**',async(r)=>{if(!failed){failed=true;await r.fulfill({status:500,contentType:'application/json',body:JSON.stringify({detail:'Falha simulada ao gravar a contagem.',field:null,errors:{}})});}else await r.continue();});
      const act=p.locator('[data-receipt-thumb] [data-operator-action-bar-action]');
      R[`${k}/acao-polegar`]=await act.getAttribute('aria-label');
      await act.click();await p.waitForTimeout(900);await shot(p,`${v}-${k}-10-erro-escrita`);
      R[`${k}/erro-escrita`]={toast:await p.evaluate(()=>[...document.querySelectorAll('[data-sonner-toast]')].map(t=>t.innerText.replace(/\s+/g,' ')).join(' / ')),...await measure(p)};
      if(await act.isVisible()&&await act.isEnabled()){await act.click();await p.waitForTimeout(900);}
      await shot(p,`${v}-${k}-11-recuperado`);R[`${k}/recuperado`]={failedOnce:failed,thumb:await p.locator('[data-receipt-thumb] [data-operator-action-bar-action]').getAttribute('aria-label').catch(()=>null)};
      await p.unroute('**/receipts/volumes/**');
    }catch(e){R[`${k}/escrita-erro`]=String(e).slice(0,300);}
    // Sem conexão
    try{
      await scenario('receiving');await go(p,'/receive');await ctx.setOffline(true);await p.evaluate(()=>window.dispatchEvent(new Event('offline')));
      await p.waitForTimeout(2500);await shot(p,`${v}-${k}-12-sem-conexao`);R[`${k}/sem-conexao`]=await measure(p);
      await ctx.setOffline(false);await p.evaluate(()=>window.dispatchEvent(new Event('online')));await p.waitForTimeout(1500);
    }catch(e){R[`${k}/offline-erro`]=String(e).slice(0,300);}
    // Leitura falhou (500 do mock) e a recuperação por "Tentar de novo"
    try{
      await scenario('error');await go(p,'/receive');await shot(p,`${v}-${k}-13-leitura-falhou`);R[`${k}/leitura-falhou`]=await measure(p);
      await scenario('receiving');await p.getByRole('button',{name:/Tentar|novo/i}).first().click();await p.waitForTimeout(1200);
      await shot(p,`${v}-${k}-14-leitura-recuperada`);R[`${k}/leitura-recuperada`]=await measure(p);
    }catch(e){R[`${k}/leitura-erro`]=String(e).slice(0,300);}
    await ctx.close();
  }
  // 3. Continuidade: Base (gerencial) → Receber (compacto em C) → Comprar → Painel, pela barra inferior.
  for(const [w,h] of [[320,568],[375,667]]){
    const k=`${w}x${h}`;const {ctx,p}=await page(v,w,h);await scenario('receiving');
    const steps=[['base-insumos','/base/materials'],['receber',null,'receive'],['base',null,'base'],['comprar',null,'buy'],['painel',null,'panel']];
    R[`${k}/continuidade`]=[];
    for(const [name,path,section] of steps){
      if(path)await go(p,path);else{await p.locator(`[data-operator-quick-bar] [data-section=${section}]`).click();await p.waitForTimeout(1200);}
      await shot(p,`${v}-${k}-cont-${R[`${k}/continuidade`].length+1}-${name}`);
      R[`${k}/continuidade`].push({step:name,url:p.url().replace(p.base,''),...await measure(p)});
    }
    await ctx.close();
  }
  // 4. Cadastros e planejamento seguem o PADRÃO: as mesmas medidas em A e C.
  {const {ctx,p}=await page(v,375,667);await scenario('normal');R.gerencial={};
    for(const path of ['/','/buy','/base/materials','/base/suppliers','/base/costs','/base/count']){await go(p,path);R.gerencial[path]=await measure(p);await shot(p,`${v}-375x667-ger${path.replace(/\//g,'_')||'_painel'}`);}
    await ctx.close();}
}
await scenario('normal');await b.close();
await writeFile(`${out}/evidence.json`,JSON.stringify(ev,null,1));
console.log('ok');
