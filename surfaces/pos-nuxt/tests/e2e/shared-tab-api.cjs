// Dois browsers independentes contra Django real; chamado pelo pytest isolado.
// Exercita transporte/auth/DB. A geometria da UI é verificada separadamente.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('@playwright/test');
(async () => {
 const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
 const browser = await chromium.launch();
 try {
  const clients = [];
  for (const cookies of fixture.cookies) {
   const context = await browser.newContext();
   await context.addCookies(cookies.map(({name,value})=>({name,value,url:fixture.url})));
   const page = await context.newPage();
   await page.goto(fixture.url + '/health/');
   clients.push(async (path, body, method='POST') => page.evaluate(async ({url,body,method}) => {
    const csrf = document.cookie.split('; ').find(c=>c.startsWith('csrftoken='))?.split('=')[1];
    const response = await fetch(url,{method,credentials:'include',headers:{'Content-Type':'application/json','X-CSRFToken':csrf || ''},...(method==='GET'?{}:{body:JSON.stringify(body)})});
    return {status:response.status, data:await response.json()};
   }, {url:fixture.url + path,body,method}));
  }
  const [tablet, pc] = clients;
  const base='/api/v1/backstage/pos/';
  const opened=await tablet(base+'tabs/77/open/',{});
  assert.equal(opened.status,200,JSON.stringify(opened));
  const payload={tab_ref:opened.data.tab_ref,tab_session_key:opened.data.session_key,expected_revision:opened.data.revision,items:[{line_id:'L-browser',sku:'BROWSER',qty:1,unit_price_q:1000}],payment_method:'cash'};
  const saved=await tablet(base+'tabs/save/',payload);
  assert.equal(saved.status,200,JSON.stringify(saved));
  const stale=await pc(base+'tabs/save/',{...payload,items:[{...payload.items[0],qty:2}]});
  assert.equal(stale.status,409,JSON.stringify(stale));
  const read=await pc(base+'tabs/77/open/',undefined,'GET');
  assert.equal(read.data.items[0].qty,1);
  assert.equal(read.data.items[0].authorship.created_by,'browser-tablet');
  const edited=await pc(base+'tabs/save/',{...payload,expected_revision:read.data.revision,items:[{...payload.items[0],qty:2}]});
  assert.equal(edited.status,200,JSON.stringify(edited));
  const current=await tablet(base+'tabs/77/open/',undefined,'GET');
  assert.equal(current.data.items[0].qty,2);
  assert.equal(current.data.items[0].authorship.updated_by,'browser-pc');
  const closeBody={...payload,expected_revision:current.data.revision,items:[{...payload.items[0],qty:2}],tendered_q:2000};
  const results=await Promise.all([tablet(base+'sale/close/',{...closeBody,client_request_id:'browser-tablet-close'}),pc(base+'sale/close/',{...closeBody,client_request_id:'browser-pc-close'})]);
  assert.deepEqual(results.map(r=>r.status).sort(),[200,409],JSON.stringify(results));
  const winner=results.findIndex(r=>r.status===200);
  const actor=winner===0?'tablet':'pc';
  const receipt=await clients[winner](base+'sale/close/?client_request_id=browser-'+actor+'-close',undefined,'GET');
  assert.equal(receipt.status,200,JSON.stringify(receipt));
  assert.equal(receipt.data.order_ref,results[winner].data.order_ref);
  const closed=await clients[1-winner](base+'tabs/77/open/',undefined,'GET');
  assert.equal(closed.status,409);
  console.log(JSON.stringify({winner:actor,order_ref:receipt.data.order_ref,close_statuses:results.map(r=>r.status)}));
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
