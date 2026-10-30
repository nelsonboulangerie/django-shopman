// PRÉVIA. Evidência A × C do Gestor (Playwright headless do node_modules da cópia).
// Uso: node evidence.mjs <orders-nuxt da cópia> <pasta de saída>
// Pré-requisito: mock em 38920, A em 4311, C em 4312 (run.sh). O cenário do mock é
// global, então A e C rodam em sequência, cada um trocando o cenário antes de ler.
import {createRequire} from 'node:module';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const [appDir,out]=process.argv.slice(2);
const {chromium}=createRequire(join(appDir,'package.json'))('playwright');
const MOCK='http://127.0.0.1:38920';
const APPS={A:'http://127.0.0.1:4311',C:'http://127.0.0.1:4312'};
const VIEWPORTS=[[320,740],[320,568],[375,667],[390,844],[1440,900]];
const scenario=(s)=>fetch(MOCK+'/__visual/scenario?set='+s);
const evidence={generated_at:new Date().toISOString(),method:'A = origin/main + apply-conn-sim; C = A + apply-compact. Mesmo mock (fixtures gravadas), build client-only.',runs:{}};

function metrics(){
  const vh=innerHeight,vw=innerWidth;
  const vis=(e)=>{const r=e.getBoundingClientRect();const cs=getComputedStyle(e);return r.width>0&&r.height>0&&cs.visibility!=='hidden';};
  const bases=[...document.querySelectorAll('[data-operator-suite-tabs],[data-exit-base-action],[data-bulk-bar]')].filter(vis).map(e=>e.getBoundingClientRect().top);
  const limit=Math.min(vh,...bases);
  const cards=[...document.querySelectorAll('article[data-card-state]')].filter(vis);
  let scroller=cards[0]?.parentElement;while(scroller&&scroller!==document.body){const o=getComputedStyle(scroller).overflowY;if(o==='auto'||o==='scroll')break;scroller=scroller.parentElement;}
  if(!cards.length)scroller=document.querySelector('main section.overflow-auto, main [class*="overflow-auto"]');
  const contentTop=scroller?Math.round(scroller.getBoundingClientRect().top):null;
  const rects=cards.map(c=>c.getBoundingClientRect());
  const full=rects.filter(r=>r.top>=(contentTop??0)-1&&r.bottom<=limit+1).length;
  const frac=rects.reduce((n,r)=>n+Math.max(0,Math.min(r.bottom,limit)-Math.max(r.top,contentTop??0))/r.height,0);
  const header=document.querySelector('[data-compact-header]');
  const headerRoot=header&&vis(header)?header:document.querySelector('[data-operator-page-header]');
  const targets=headerRoot?[...headerRoot.querySelectorAll('button,a')].filter(vis).filter(e=>!e.closest('[aria-hidden="true"]')).map(e=>{const r=e.getBoundingClientRect();return{name:(e.getAttribute('aria-label')||e.textContent.trim()).slice(0,60),w:Math.round(r.width),h:Math.round(r.height)};}):[];
  const firstContent=document.querySelector('main [data-detail-main], main section [class]');
  return{viewport:`${vw}x${vh}`,contentTop,firstCardTop:rects[0]?Math.round(rects[0].top):null,firstCardHeight:rects[0]?Math.round(rects[0].height):null,
    cardsFullyVisible:full,cardsVisibleFraction:Math.round(frac*100)/100,topChrome:contentTop,baseChrome:Math.round(vh-limit),
    scrollWidth:document.documentElement.scrollWidth,horizontalOverflow:document.documentElement.scrollWidth>vw,
    headerTargets:targets,headerTargetsUnder44:targets.filter(t=>t.w<44||t.h<44).map(t=>`${t.name} ${t.w}x${t.h}`),
    attentionStrip:!!document.querySelector('[data-compact-attention]'),
    activeStrip:document.querySelector('[data-compact-active]')?.textContent.trim().replace(/\s+/g,' ')||null,
    pageText:document.querySelector('[data-queue-error]')?.textContent.trim().replace(/\s+/g,' ').slice(0,120)||null};
}

const browser=await chromium.launch();
async function page(app,w,h,path='/'){
  const p=await browser.newPage({viewport:{width:w,height:h}});
  await p.goto(APPS[app]+path);await p.waitForTimeout(2500);await p.evaluate(()=>document.fonts.ready);
  return p;
}
async function shot(p,app,name,extra={}){
  await p.waitForTimeout(500);
  await p.screenshot({path:join(out,`${app}-${name}.png`)});
  const m={...await p.evaluate(metrics),...extra};
  (evidence.runs[app]??={})[name]=m;return m;
}
async function click(p,sel){const l=p.locator(sel).filter({visible:true}).first();await l.click({timeout:4000});await p.waitForTimeout(500);}
async function tryStep(app,name,fn){try{await fn();}catch(e){(evidence.runs[app]??={})[name]={error:String(e.message).split('\n')[0]};}}

for(const app of ['A','C']){
  await scenario('normal');
  for(const [w,h] of VIEWPORTS){const p=await page(app,w,h);await shot(p,app,`board-${w}x${h}`);await p.close();}
  await scenario('dense');
  for(const [w,h] of [[320,568],[375,667]]){const p=await page(app,w,h);await shot(p,app,`dense-${w}x${h}`);await p.close();}
  await scenario('normal');
  for(const [w,h] of [[320,568],[375,667]]){
    const p=await page(app,w,h);
    const visto=app==='C'?'[data-compact-visto]':'[data-page-header-icon-action][aria-label="Visto"]';
    await tryStep(app,`after-visto-${w}x${h}`,async()=>{await click(p,visto);await shot(p,app,`after-visto-${w}x${h}`);});
    await p.close();
  }
  // Interações a 320x568 (o caso apertado)
  let p=await page(app,320,568);
  await tryStep(app,'options-open',async()=>{await click(p,app==='C'?'[data-compact-options]':'[data-page-header-more] button, button[data-page-header-more]');await shot(p,app,'options-open');await p.keyboard.press('Escape');});
  await tryStep(app,'avisos-open',async()=>{await click(p,app==='C'?'[data-compact-header] [data-compact-inbox] button, [data-compact-header] button[aria-label*="viso"]':'[data-page-header-inbox] button');await shot(p,app,'avisos-open');await p.keyboard.press('Escape');});
  await tryStep(app,'filters-open',async()=>{await click(p,app==='C'?'[data-compact-bar] button[aria-label^="Filtros"]':'[data-page-header-filters-open]');await shot(p,app,'filters-open');
    await click(p,'[role="dialog"] [data-fulfillment-filters] button:has-text("Entrega"), [role="dialog"] [data-fulfillment-filters] [role="radio"]:has-text("Entrega"), [role="dialog"] button:has-text("Entrega")');
    await click(p,app==='C'?'[role="dialog"] button:has-text("Ver resultados")':'[data-page-header-filters-done]');
    await shot(p,app,'filter-active');});
  await tryStep(app,'filter-cleared',async()=>{await click(p,app==='C'?'[data-compact-active] button':'[data-page-header-active-filter]');await shot(p,app,'filter-cleared');});
  await tryStep(app,'search-dialog',async()=>{
    if(app==='C')await click(p,'[data-compact-bar] button[aria-label^="Buscar"]');else await p.keyboard.press('/');
    await p.waitForTimeout(400);await p.keyboard.type('Maria');await p.waitForTimeout(600);await shot(p,app,'search-dialog');await p.keyboard.press('Enter');await p.waitForTimeout(400);await shot(p,app,'search-active');});
  await p.close();
  p=await page(app,320,568,'/?q=Maria');await shot(p,app,'search-active-url');
  await tryStep(app,'search-cleared',async()=>{await click(p,app==='C'?'[data-compact-active] button':'[data-page-header-active-filter], [data-page-header-search] button[aria-label*="impar"]');await shot(p,app,'search-cleared');});
  await p.close();
  // Conexão: simulação (?conn=) e erro real de leitura (cenário error)
  for(const c of ['live','late','off']){p=await page(app,320,568,'/?conn='+c);await shot(p,app,'conn-'+c);await p.close();}
  await scenario('error');p=await page(app,320,568);await shot(p,app,'read-error');
  await scenario('normal');await tryStep(app,'read-recovered',async()=>{await p.waitForTimeout(31000);await shot(p,app,'read-recovered');});await p.close();
  // Erro de escrita (409 do ERR07 na galeria) e recuperação
  await scenario('gallery');p=await page(app,320,568);
  await shot(p,app,'urgent-alert');
  await tryStep(app,'urgent-alert-seen',async()=>{await click(p,'[role="alertdialog"] button:has-text("Visto"), [role="dialog"] button:has-text("Visto")');await p.waitForTimeout(600);});
  await tryStep(app,'write-error',async()=>{
    for(const tab of ['Entrada','Preparo','Saída']){if(await p.locator('article[data-card-state]:has-text("Fábio")').filter({visible:true}).count())break;await p.locator('[data-board-zone-tabs] [role="tab"]',{hasText:tab}).first().click();await p.waitForTimeout(400);}
    const card=p.locator('article[data-card-state]:has-text("Fábio")').filter({visible:true}).first();await card.scrollIntoViewIfNeeded();
    await card.locator('[data-card-primary] button, button[data-card-primary]').first().click({timeout:4000});await p.waitForTimeout(1200);
    await shot(p,app,'write-error');
    const dismiss=card.locator('[data-card-error] button').first();if(await dismiss.count()){await dismiss.click();await p.waitForTimeout(500);await shot(p,app,'write-error-dismissed');}
  });
  await p.close();await scenario('normal');
  // Detalhe (tela de registro)
  for(const [w,h] of [[320,568],[375,667],[1440,900]]){p=await page(app,w,h,'/WEB-261006-F90');await shot(p,app,`detail-${w}x${h}`);await p.close();}
  p=await page(app,320,568,'/WEB-261006-F90');
  await tryStep(app,'detail-menu',async()=>{await click(p,'[data-action="menu-phone"]');await shot(p,app,'detail-menu');});await p.close();
}
// Variante de Avisos no ⋮ (só C)
await scenario('normal');
let p=await page('C',320,568,'/?avisos=options');await shot(p,'C','avisos-in-options-closed');
await tryStep('C','avisos-in-options',async()=>{await click(p,'[data-compact-options]');await shot(p,'C','avisos-in-options');});await p.close();
await browser.close();
await writeFile(join(out,'evidence.json'),JSON.stringify(evidence,null,1));
console.log('ok');
