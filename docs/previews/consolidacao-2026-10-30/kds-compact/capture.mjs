// Evidência da prévia (Playwright headless). Uso: node capture.mjs <node_modules com playwright> <saída>
import {createRequire} from 'node:module';
import {writeFile} from 'node:fs/promises';
const [nm,out]=process.argv.slice(2);
const {chromium}=createRequire(nm+'/')('playwright');
const V={A:'http://127.0.0.1:4291',B:'http://127.0.0.1:4292',C:'http://127.0.0.1:4293'};
const sizes=[[320,740],[320,568],[375,667],[390,844],[1440,900]];
const browser=await chromium.launch();const ev={};
async function page(w,h){const ctx=await browser.newContext({viewport:{width:w,height:h},colorScheme:'dark',deviceScaleFactor:2,hasTouch:w<768,isMobile:w<768});
 await ctx.addInitScript(()=>{try{localStorage.setItem('kds-pwa-invite-dismissed','1')}catch{}});return ctx.newPage();}
async function settle(p){await p.waitForTimeout(1800);const b=p.getByRole('button',{name:'Agora não'});if(await b.count())await b.first().click().catch(()=>{});await p.waitForTimeout(500);}
const measure=p=>p.evaluate(()=>{const all=[...document.querySelectorAll('main *')];const agora=all.find(e=>e.childElementCount===0&&e.textContent.trim()==='Agora');
 const pronto=[...document.querySelectorAll('button')].find(b=>/^Pronto \d/.test(b.textContent.trim())&&b.offsetParent);
 const vis=s=>[...document.querySelectorAll(s)].filter(e=>e.offsetParent).map(e=>{const r=e.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)]});
 return {agoraTop:agora?Math.round(agora.getBoundingClientRect().top):null,prontoTop:pronto?Math.round(pronto.getBoundingClientRect().top):null,
  usefulBetween:agora&&pronto?Math.round(pronto.getBoundingClientRect().top-agora.getBoundingClientRect().top):null,
  scrollWidth:document.documentElement.scrollWidth,compactBar:vis('[data-compact-bar]')[0]||null,compactTargets:vis('[data-compact-bar] button')}});
for(const [k,u] of Object.entries(V))for(const [w,h] of sizes){const p=await page(w,h);await p.goto(u+'/bancada?conn=calm');await settle(p);
 ev[`${k}-${w}x${h}`]=await measure(p);await p.screenshot({path:`${out}/${k}-${w}x${h}.png`});await p.context().close();}
for(const k of ['A','C'])for(const st of ['off','live']){const p=await page(320,740);await p.goto(V[k]+'/bancada?conn='+st);await settle(p);await p.screenshot({path:`${out}/${k}-conn-${st}-320.png`});await p.context().close();}
{const p=await page(320,740);await p.goto(V.C+'/bancada?conn=calm');await settle(p);await p.getByRole('button',{name:/^Opções: Cozinha/}).click();await p.waitForTimeout(600);await p.screenshot({path:`${out}/C-options-320.png`});await p.context().close();}
{const p=await page(320,740);await p.goto(V.C+'/bancada?conn=calm&avisos=options');await settle(p);ev['C-avisos-options-320']=await measure(p);await p.screenshot({path:`${out}/C-avisos-options-320.png`});await p.context().close();}
{const p=await page(320,740);await p.goto(V.C+'/bancada?conn=calm');await settle(p);await p.getByRole('button',{name:'Filtros',exact:true}).click();await p.waitForTimeout(700);await p.screenshot({path:`${out}/C-filters-320.png`});await p.context().close();}
await writeFile(out+'/evidence.json',JSON.stringify(ev,null,1));await browser.close();console.log(JSON.stringify(ev));
