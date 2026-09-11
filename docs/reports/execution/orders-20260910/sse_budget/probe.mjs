import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {resolve, basename} from 'node:path';
import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import os from 'node:os';
const root=process.cwd();assert.equal(basename(root),'django-shopman-orders-execution-20260910');
const require=createRequire(resolve('surfaces/orders-nuxt/package.json'));
const {chromium,expect}=require('@playwright/test');
const {ref}=JSON.parse(readFileSync('.orders-lab/legacy-manifest.json','utf8'));
const audit=()=>JSON.parse(execFileSync('/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python',['docs/reports/execution/orders-20260910/command_budget/audit_note.py',ref],{encoding:'utf8'}));
const before=audit();const samples=[];const browser=await chromium.launch();
try {
 const page=await browser.newPage({baseURL:'http://127.0.0.1:3007',viewport:{width:1440,height:1000}});
 await page.addInitScript(()=>{const Original=window.EventSource;window.orderPushes=0;window.EventSource=class extends Original {constructor(...args){super(...args);this.addEventListener('backstage-orders-update',()=>window.orderPushes++);}};});
 await page.goto('/');await page.getByRole('textbox',{name:'Usuário',exact:true}).fill('orders-lab');await page.getByLabel('Senha',{exact:true}).fill('synthetic-lab-only-20260910');await page.getByRole('button',{name:'Entrar',exact:true}).click();await page.getByRole('heading',{name:'Entre para operar'}).waitFor({state:'hidden'});
 const stream=page.waitForResponse(r=>r.url().endsWith('/sse/orders'));
 await page.goto('/'+ref);assert.equal((await stream).status(),200);
 const note=page.getByPlaceholder('Instruções de preparo para a cozinha…');await expect(note).toBeVisible();
 const path='/api/v1/backstage/orders/'+ref+'/';
 const stamp=Date.now();
 for(let index=0;index<20;index++){
  const observed=await (await page.request.get(path)).json();const action=observed.order.actions.find(a=>a.ref==='notes');assert.ok(action?.enabled);
  const value='Synthetic SSE '+stamp+' '+index;
  const pushes=await page.evaluate(()=>window.orderPushes);
  const start=performance.now();
  const response=await page.request.post(path+'notes/',{headers:{'Idempotency-Key':crypto.randomUUID()},data:{...action.payload_schema,notes:value}});
  assert.equal(response.status(),200);assert.equal((await response.json()).outcome,'applied');
  await page.waitForFunction(expected=>document.querySelector('#order-notes')?.value===expected,value,{timeout:5000});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const bound=performance.now()-start;
  const afterPush=await page.evaluate(()=>window.orderPushes);assert.ok(afterPush>pushes,'Actual SSE must arrive; polling alone is not proof');
  samples.push({index,command_start_to_visible_two_frames_ms:bound,pushes:afterPush-pushes});
 }
 const after=audit();assert.equal(after.kitchen_note_events-before.kitchen_note_events,20);
 const values=samples.map(s=>s.command_start_to_visible_two_frames_ms).sort((a,b)=>a-b);
 const result={source:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),uncommitted_ui:'catalog minimum width only',environment:{cpu:os.cpus()[0].model,logical_cpus:os.cpus().length,memory_bytes:os.totalmem(),node:process.version,chromium:browser.version(),viewport:[1440,1000],network:'localhost',remote_providers:false},samples,n:20,p50_ms:values[9],p95_ms:values[18],max_ms:values[19],canonical_events_added:20,scope:'Upper bound from before POST to visible note plus two animation frames. Commit is inside this interval. One synthetic resource, warm stream, not pilot network or human time.'};
 writeFileSync('.orders-lab/sse-budget.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));assert.ok(result.p95_ms<=2000,'Proposed SSE budget exceeded');
}finally{await browser.close()}
