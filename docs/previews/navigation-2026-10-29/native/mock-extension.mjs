// Exclusivo da prévia: estados em memória, sem efeitos em integrações reais.
orders.sort((a,b)=>a.commitment_date.localeCompare(b.commitment_date)||(a.window_start||'99').localeCompare(b.window_start||'99'));
const previewOriginalOrders = structuredClone(orders);
// Datas relativas ao cenário, sem misturar setembro com o dia corrente.
function previewDates(value) {
  for(const key of Object.keys(value||{})) {
    if(typeof value[key]==='string')value[key]=value[key].replace(/2026-09-29/g,TODAY).replace(/2026-09-28/g,addDays(TODAY,-1)).replace(/2026-09-30/g,addDays(TODAY,1)).replace(/29\/09(?:\/2026)?/g,ddmm(TODAY));
    else if(value[key]&&typeof value[key]==='object')previewDates(value[key]);
  }
}
for(const value of [pos.cash_runtime,cashReport,dayClosing,seating])previewDates(value);
for(const z of cashReport.z_readings)Object.assign(z,{sales_count:cashReport.day_totals.sales_count,sales_total_q:cashReport.day_totals.sales_total_q,sales_total_display:cashReport.day_totals.sales_total_display,sales_by_method:structuredClone(cashReport.day_totals.sales_by_method),movements_in_q:0,movements_in_display:'0,00',movements_out_q:0,movements_out_display:'0,00',opened_at:`${TODAY}T06:00:00-03:00`,closed_at:`${TODAY}T07:00:00-03:00`});
pos.managers=[{username:'demo',name:'Gerência de demonstração',has_pin:true}];
const previewInitial = structuredClone({settings,seating,dayClosing,cashRuntime:pos.cash_runtime,cashReport,rides:RIDES,products:pos.products});
const previewDetails = new Map();
const previewCompleted = [];
const previewViews = [{ id: 1, surface: 'pos', screen: 'preorders', name: 'Entregas a receber', query: { filters: { fulfillment: ['delivery'], pay: ['to_receive'] } }, pinned: true }];
const previewBaseViews=structuredClone(previewViews);
const previewRequests = [];
const previewOnce = new Map();
const previewEditTabs = new Map();
let previewFailure = null;
let previewSeq = 100;
const clone = (value) => structuredClone(value);
function previewDetail(ref) {
  if (previewDetails.has(ref) && !RIDES[ref]) return previewDetails.get(ref);
  const c = orders.find(o => o.ref === ref) || previewCompleted.find(o => o.ref === ref);
  if (!c) return null;
  const d = RIDES[ref] ? clone(rideDetail(ref)) : clone(preorderDetail);
  Object.assign(d, { ref, customer_name: c.customer_name, total_display: c.total_display,
    fulfillment_type: c.fulfillment_type, fulfillment_label: c.fulfillment_label,
    channel_name: c.channel_label, customer_phone: '(43) 99988-7766', customer_email: '',
    customer_phone_uri: '', customer_whatsapp_url: '',
    payment_status_label: c.payment_state === 'paid' ? 'Pago' : 'Pendente' });
  d.counter.card = c; d.managers=pos.managers;
  d.counter.hand_over.needs_payment = (c.balance_q || 0) > 0;
  d.counter.hand_over.amount_q = c.balance_q || 0;
  d.counter.hand_over.amount_display = brl(c.balance_q || 0);
  d.counter.reschedule.date = c.commitment_date;
  d.schedule_label = `${ddmm(c.commitment_date)} · ${c.window_label}`;
  // Soma e quantidade coerentes. Não usar as 12 linhas de estresse da fixture visual.
  d.items = [{ sku: 'KIT-BRUNCH', name: 'Kit brunch', qty: '1', unit_price_display: brl(c.total_q - 2400), total_display: brl(c.total_q - 2400) },
    { sku: 'CROISSANT', name: 'Croissant', qty: '2', unit_price_display: brl(1200), total_display: brl(2400) }];
  if(ref==='NB-1043')d.items=[{sku:'KIBIXINHA',name:'Kibixinha',qty:'2',unit_price_display:brl(5000),total_display:brl(10000)},{sku:'SUCO',name:'Suco',qty:'1',unit_price_display:brl(2400),total_display:brl(2400)}];
  else if(RIDES[ref])d.items=[{sku:'QUICHE',name:'Quiche de alho-poró',qty:'1',unit_price_display:brl(5000),total_display:brl(5000)},{sku:'BAGUETE',name:'Baguete',qty:'2',unit_price_display:brl(2400),total_display:brl(4800)}];
  else if(ref==='IFOOD-8821')d.items=[{sku:'CESTA',name:'Cesta café da manhã',qty:'1',unit_price_display:brl(5900),total_display:brl(5900)}];
  d.counter.revision = 'preview-1'; d.counter.reschedule.revision = 'preview-1';
  previewDetails.set(ref,d); return d;
}
function previewTimeline(d, label, detail = '') {
  d.timeline.push({ event_type:'comment', label, detail, actor:'Ana (demonstração)', timestamp_display:`${ddmm(TODAY)} às 12:00` });
  d.counter.revision = `preview-${++previewSeq}`;
  d.counter.reschedule.revision = d.counter.revision;
}
function previewError(res,status,detail,field='',code='preview_validation') {
  send(res,status,{detail,field,errors:[],error:{code,message:detail}}); return true;
}
function previewManager(body,res) {
  if(!body.manager_approval){previewError(res,403,'Peça a assinatura da gerência de demonstração.','', 'manager_approval_required');return false;}
  if(body.manager_approval.username!=='demo'||body.manager_approval.pin!=='0000'){previewError(res,403,'PIN de demonstração incorreto. Use o PIN fictício 0000.','', 'manager_approval_invalid');return false;}
  return true;
}
async function previewHandle(req,res,url) {
  const controlPath=url.pathname.startsWith('/api/v1/backstage/__preview/')
    ? url.pathname.replace('/api/v1/backstage/__preview/','/__preview/') : url.pathname;
  const path=controlPath.startsWith('/__preview/') ? controlPath.replace(/\/$/,'') : controlPath;
  if(path==='/__preview/state') {send(res,200,{orders,completed:previewCompleted,requests:previewRequests});return true;}
  if(path==='/__preview/reset' && req.method==='POST') {
    orders.splice(0,orders.length,...clone(previewOriginalOrders));previewDetails.clear();previewEditTabs.clear();previewViews.splice(0,previewViews.length,...clone(previewBaseViews));previewCompleted.length=0;previewOnce.clear();previewFailure=null;
    Object.assign(settings,clone(previewInitial.settings));Object.assign(seating,clone(previewInitial.seating));Object.assign(dayClosing,clone(previewInitial.dayClosing));Object.assign(cashReport,clone(previewInitial.cashReport));pos.cash_runtime=clone(previewInitial.cashRuntime);pos.products=clone(previewInitial.products);pos.has_open_cash_session=true;Object.assign(RIDES,clone(previewInitial.rides));
    send(res,200,{ok:true});return true;
  }
  if(path==='/__preview/fail-next' && req.method==='POST') { previewFailure=await readBody(req);send(res,200,{ok:true});return true; }
  if(!path.startsWith('/api/')) return false;
  previewRequests.push({method:req.method,path});
  if(previewFailure && (!previewFailure.path || path.includes(previewFailure.path)) && (!previewFailure.method || req.method===previewFailure.method)) {
    const failure=previewFailure;previewFailure=null;
    return previewError(res,failure.status||503,failure.detail||'Falha simulada. Os dados continuam preservados.');
  }

  if(path==='/api/v1/backstage/pos/') {
    const routes={open_cash_shift:'cash/open',close_cash_shift:'cash/close',cash_movement:'cash/movement',request_change:'cash/change-request',drawer_open:'cash/drawer-open'};
    for(const [ref,route] of Object.entries(routes))if(!pos.actions.some(a=>a.ref===ref))pos.actions.push({ref,kind:'mutation',enabled:true,reason:'',href:`/api/v1/backstage/pos/${route}/`,method:'POST'});
    send(res,200,{pos,shift:{count:(cashReport.x_reading?.sales_count||0)+cashReport.z_readings.reduce((n,z)=>n+z.sales_count,0),total_q:(cashReport.x_reading?.sales_total_q||0)+cashReport.z_readings.reduce((n,z)=>n+z.sales_total_q,0),total_display:brl((cashReport.x_reading?.sales_total_q||0)+cashReport.z_readings.reduce((n,z)=>n+z.sales_total_q,0))},tabs:TABS,operator:{id:7,name:'Ana'}});return true;
  }
  const editStart=path.match(/^\/api\/v1\/backstage\/pos\/preorders\/([^/]+)\/edit-session\/$/);
  if(editStart&&req.method==='POST') {
    await readBody(req);const d=previewDetail(editStart[1]);if(!d)return previewError(res,404,'Encomenda não encontrada.');
    const tab=clone(tabPayload('15'));
    tab.items=[{...clone(tabPayload('12').items[0]),qty:1,price_q:d.counter.card.total_q,line_id:'preview-original',name:d.items[0].name}];
    tab.sales_mode='order';tab.customer_name=d.customer_name;tab.fulfillment_type=d.fulfillment_type;tab.delivery_date=d.counter.reschedule.date;tab.delivery_time_slot=d.counter.reschedule.slot;
    previewEditTabs.set(d.ref,tab);
    send(res,200,{ok:true,tab,edit:{order_ref:d.ref,base_revision:d.counter.revision,actor_id:7,original:{items:tab.items,fulfillment_type:d.fulfillment_type,delivery_address:'',delivery_address_structured:{},delivery_date:tab.delivery_date,delivery_time_slot:tab.delivery_time_slot,order_notes:d.customer_note||'',fiscal_tax_id:''}}});return true;
  }
  const edit=path.match(/^\/api\/v1\/backstage\/orders\/([^/]+)\/edit\/(preview\/)?$/);
  if(edit&&req.method==='POST') {
    const body=await readBody(req),d=previewDetail(edit[1]),tab=previewEditTabs.get(edit[1]);
    if(!d||!tab)return previewError(res,409,'Abra a edição novamente.');
    const items=(body.items||[]).map((i)=>{const old=tab.items.find(x=>x.line_id===i.line_id),product=pos.products.find(p=>p.sku===i.sku);const price=old?.price_q??product?.price_q??0;return {...i,name:old?.name||product?.name||i.sku,unit_price_q:price,line_total_q:Math.round(price*Number(i.qty)),is_new:!old,is_delivery_fee:false};});
    if(!items.length||items.some(i=>Number(i.qty)<=0))return previewError(res,422,'A encomenda precisa ter itens com quantidade válida.','items');
    const total=items.reduce((n,i)=>n+i.line_total_q,0),difference=total-d.counter.card.total_q;
    const preview={changed:difference!==0||body.notes!=null,items_changed:difference!==0,items,previous_total_q:d.counter.card.total_q,total_q:total,difference_q:difference,notes:{before:d.customer_note,after:body.notes??d.customer_note,changed:body.notes!=null},fulfillment:{before:d.fulfillment_type,after:body.fulfillment_type||d.fulfillment_type,changed:false,delivery_address:'',delivery_fee_before_q:0,delivery_fee_after_q:0},schedule:{changed:false,date:d.counter.reschedule.date,slot:d.counter.reschedule.slot},settlement:{kind:'none',amount_q:0,method:''},balance_before_q:d.counter.card.balance_q,balance_after_q:Math.max(0,d.counter.card.balance_q+difference),requires_manager_approval:false,customer_note:'Alterações da demonstração, sem envio ao cliente.'};
    if(!edit[2]){if(body.base_revision!==d.counter.revision)return previewError(res,409,'A encomenda mudou. Abra a edição novamente.');Object.assign(d.counter.card,{total_q:total,total_display:brl(total),balance_q:preview.balance_after_q,balance_display:brl(preview.balance_after_q)});d.total_display=brl(total);d.items=items.map(i=>({sku:i.sku,name:i.name,qty:String(i.qty),unit_price_display:brl(i.unit_price_q),total_display:brl(i.line_total_q)}));d.customer_note=preview.notes.after;previewTimeline(d,'Encomenda editada');}
    send(res,200,{ok:true,ref:d.ref,base_revision:d.counter.revision,revision:previewSeq,changed:preview.changed,preview});return true;
  }
  if(path==='/api/v1/backstage/pos/schedule/') {
    const date=url.searchParams.get('date')||TODAY;
    send(res,200,{ok:true,today:TODAY,date,max_preorder_days:30,available_dates:Array.from({length:31},(_,i)=>addDays(TODAY,i)),
      windows:[{ref:'slot-09',label:'9h às 10h',enabled:date!==TODAY,reason:date===TODAY?'O preparo não fica pronto a tempo.':''},
        {ref:'slot-12',label:'12h às 13h',enabled:true},{ref:'slot-15',label:'15h às 16h',enabled:true}],
      earliest_window_ref:'slot-12',ready_at:'12:00',bottleneck_name:'Forno',grid:'canonical',is_today:date===TODAY,readiness_unavailable:false});return true;
  }
  if(path==='/api/v1/backstage/pos/preorders/search/') {
    const q=(url.searchParams.get('q')||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const match=o=>`${o.customer_name} ${o.ref} ${o.items_summary} 43999887766`.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q);
    const open=orders.filter(match), completed=url.searchParams.get('include_completed')==='1'||url.searchParams.get('include_completed')==='true'?previewCompleted.filter(match):[];
    send(res,200,{ok:true,query:url.searchParams.get('q')||'',today:TODAY,include_completed:url.searchParams.get('include_completed')==='1',completed_days:30,open_count:open.length,open,completed_count:completed.length,completed});return true;
  }
  if(path==='/api/v1/backstage/search/') {
    const query=url.searchParams.get('q')||'',normal=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const results=orders.filter(o=>normal(o.customer_name+' '+o.ref).includes(normal(query))).map(o=>({key:o.ref,type:'order',app:'pos',app_label:'PDV',place:'Encomendas',title:o.customer_name,detail:o.ref+' · '+o.total_display,url:`/preorders/${encodeURIComponent(o.ref)}`,icon:'i-lucide-calendar-clock'}));
    send(res,200,{search:{query,searched:query.length>=2,total:results.length,groups:[{type:'orders',label:'Encomendas',results}],apps:[{ref:'pos',label:'PDV',count:results.length}]}});return true;
  }
  const detailRoute=path.match(/^\/api\/v1\/backstage\/pos\/preorders\/([^/]+)\/$/);
  if(detailRoute) {
    const d=previewDetail(decodeURIComponent(detailRoute[1]));
    if(!d)return previewError(res,404,'Esta encomenda não existe na demonstração.');
    send(res,200,{order:d,generated_at:`${TODAY}T12:00:00Z`,contract_version:1});return true;
  }
  const gesture=path.match(/^\/api\/v1\/backstage\/(?:pos\/preorders|orders)\/([^/]+)\/(reschedule|comment|cancel|hand-over|payment\/check|redo-tab)\/$/);
  if(gesture && req.method==='POST') {
    const d=previewDetail(gesture[1]);if(!d)return previewError(res,404,'Encomenda não encontrada.');
    const body=await readBody(req),kind=gesture[2],key=body.client_request_id||body.idempotency_key;
    if(key&&previewOnce.has(key)){send(res,200,previewOnce.get(key));return true;}
    const c=d.counter.card;
    if(body.base_revision && !['comment','payment/check','redo-tab'].includes(kind) && body.base_revision!==d.counter.revision && body.base_revision!==d.counter.reschedule.revision)
      return previewError(res,409,'A encomenda mudou. Atualize antes de repetir.');
    let response={ok:true,ref:d.ref};
    if(kind==='reschedule') {
      if(!/^\d{4}-\d{2}-\d{2}$/.test(body.date||'')||body.date<TODAY||body.date>addDays(TODAY,30))return previewError(res,422,'Escolha uma data disponível.','date');
      if(body.slot==='slot-09'&&body.date===TODAY)return previewError(res,422,'O preparo não fica pronto a tempo.','slot');
      const previous=c.commitment_date, oldSlot=d.counter.reschedule.slot;
      c.commitment_date=body.date;c.commitment_date_display=ddmm(body.date);c.window_start=body.slot==='slot-15'?'15:00':body.slot==='slot-09'?'09:00':body.slot?'12:00':'';
      c.window_label=body.slot==='slot-15'?'15h às 16h':body.slot==='slot-09'?'9h às 10h':body.slot?'12h às 13h':'A combinar';
      d.counter.reschedule.date=body.date;d.counter.reschedule.slot=body.slot||'';d.schedule_label=`${ddmm(body.date)} · ${c.window_label}`;
      previewTimeline(d,'Data combinada alterada',body.reason||'');response={...response,changed:previous!==body.date||oldSlot!==(body.slot||''),activated_now:false};
    }
    if(kind==='comment') {if(!body.note?.trim())return previewError(res,422,'Escreva o comentário.','note');previewTimeline(d,'Comentário',body.note);}
    if(kind==='hand-over') {
      if(!d.counter.hand_over.allowed)return previewError(res,409,'Esta encomenda não pode ser entregue novamente.');
      const paid=(body.tenders||[]).reduce((n,t)=>n+Number(t.amount_q||0),0);
      if(c.balance_q>0&&paid<c.balance_q)return previewError(res,422,'O valor recebido não cobre o saldo.','tenders');
      response.received_q=c.balance_q||0;response.fiscal_state='not_required';c.balance_q=0;c.balance_display=brl(0);c.payment_state='paid';c.situation='delivered';c.situation_label='Entregue';d.status='fulfilled';d.status_label='Entregue';
      d.counter.edit.allowed=false;d.counter.edit.block_reason='A encomenda já foi entregue.';d.counter.hand_over.allowed=false;d.counter.hand_over.needs_payment=false;d.counter.hand_over.amount_q=0;d.counter.cancel.allowed=false;d.counter.reschedule.allowed=false;
      previewTimeline(d,'Encomenda entregue');const i=orders.indexOf(c);if(i>=0)orders.splice(i,1);previewCompleted.push(c);
    }
    if(kind==='cancel') {
      if(!d.counter.cancel.allowed)return previewError(res,409,'Esta encomenda não pode ser cancelada novamente.');
      if(c.payment_state==='paid'&&!previewManager(body,res))return true;
      if(!body.reason_key)return previewError(res,422,'Escolha o motivo do cancelamento.','reason_key');
      d.counter.edit.allowed=false;d.counter.edit.block_reason='A encomenda foi cancelada.';d.status='cancelled';d.status_label='Cancelado';c.status='cancelled';c.situation='cancelled';c.situation_label='Cancelado';
      d.counter.hand_over.allowed=false;d.counter.cancel.allowed=false;d.counter.reschedule.allowed=false;
      previewTimeline(d,'Encomenda cancelada',body.internal_note||body.reason_key);const i=orders.indexOf(c);if(i>=0)orders.splice(i,1);previewCompleted.push(c);
    }
    if(kind==='payment/check') response.changed=false;
    if(kind==='redo-tab'){response.tab=tabPayload('15');response.redo={order_ref:d.ref,resumed:false,schedule_dropped:''};}
    if(key)previewOnce.set(key,response);send(res,200,response);return true;
  }
  if(path==='/api/v1/backstage/saved-views/') {
    if(req.method==='POST'){const body=await readBody(req);if(!body.name?.trim())return previewError(res,422,'Dê um nome ao favorito.','name');const view={...body,id:++previewSeq};previewViews.push(view);send(res,201,{view});}
    else send(res,200,{views:previewViews});return true;
  }
  const saved=path.match(/^\/api\/v1\/backstage\/saved-views\/(\d+)\/$/);
  if(saved){const i=previewViews.findIndex(v=>v.id===Number(saved[1]));if(i<0)return previewError(res,404,'Favorito não encontrado.');if(req.method==='DELETE')previewViews.splice(i,1);else Object.assign(previewViews[i],await readBody(req));send(res,200,{ok:true,view:previewViews[i]});return true;}
  if(path==='/api/v1/backstage/pos/settings/'&&req.method==='POST') {
    const body=await readBody(req);
    if(body.section==='printer'){const p=settings.printers.find(p=>p.terminal_ref===body.terminal_ref);if(!p)return previewError(res,404,'Impressora não encontrada.');Object.assign(p,{roll_width_mm:body.roll_width_mm,cut_mode:body.cut_mode});}
    else if(body.section==='card_machine'){if(!body.label?.trim())return previewError(res,422,'Informe o nome da maquininha.','label');let m=settings.card_machines.find(m=>m.ref===body.ref);if(m?.with_order&&body.active===false)return previewError(res,409,'Esta maquininha está em uma entrega. Registre a volta antes de desativar.');if(m)Object.assign(m,body);else settings.card_machines.push({...body,ref:`MAQ-${++previewSeq}`,with_order:''});}
    else if(body.section==='card_machine_toggle'){const m=settings.card_machines.find(m=>m.ref===body.ref);if(m)m.active=body.active;}
    else if(body.section==='shortcuts')Object.assign(settings.shortcuts,body);
    else if(body.section==='kitchen_station'){const s=settings.kitchen_stations.find(s=>s.ref===body.station_ref);if(s){s.auto_fire=!!body.auto_fire;for(const product of pos.products||[])if(product.kitchen_station===s.name)product.kitchen_auto_fire=s.auto_fire;}}
    else return previewError(res,422,'Seção não reconhecida no simulador.','section');
    send(res,200,settings);return true;
  }
  if(path==='/api/v1/backstage/pos/seating/'&&req.method==='POST') {
    const body=await readBody(req);if(body.revision&&body.revision!==seating.revision)return previewError(res,409,'A planta mudou. Atualize antes de salvar.');
    // O contrato usa operações, não substituição cega de toda a planta.
    seating.spots=seating.spots.filter(s=>!(body.removed||[]).includes(s.ref));
    for(const change of body.spots||[]) {
      const i=seating.spots.findIndex(s=>s.ref===change.ref);
      if(i>=0)Object.assign(seating.spots[i],change);
      else seating.spots.push({...seatingSpot(`M-${++previewSeq}`,change.label||'Mesa nova',change.area||'Salão',change.shape||'square',change.seats||2,change.plan_x||0,change.plan_y||0),...change,born_today:true});
    }
    seating.totals={capacity_seats:seating.spots.filter(s=>s.counts_in_capacity).reduce((n,s)=>n+s.seats,0),capacity_spots:seating.spots.filter(s=>s.counts_in_capacity).length,extra_seats:seating.spots.filter(s=>!s.counts_in_capacity).reduce((n,s)=>n+s.seats,0)};
    seating.history.push({id:++previewSeq,at:`${TODAY}T12:00:00Z`,at_label:'Agora',who:'Ana',ref:'',action:'update',summary:'Planta atualizada na demonstração',before:null,after:null});
    if(body.fixtures)seating.fixtures=body.fixtures;seating.revision=`preview-${++previewSeq}`;send(res,200,seating);return true;
  }
  if(path==='/api/v1/backstage/closing/'&&req.method==='POST') {
    const body=await readBody(req);if(dayClosing.already_closed)return previewError(res,409,'O dia já foi fechado.');
    if(!body.quantities||dayClosing.items.some(i=>body.quantities[i.sku]==null||body.quantities[i.sku]===''||!Number.isInteger(Number(body.quantities[i.sku]))||Number(body.quantities[i.sku])<0))return previewError(res,422,'Preencha a contagem de cada item.','quantities');
    dayClosing.already_closed=true;dayClosing.existing_closing_display=`${ddmm(TODAY)} · Ana`;send(res,200,{ok:true});return true;
  }
  const episode=path.match(/^\/api\/v1\/backstage\/closing\/episodes\/(\d+)\/$/);
  if(episode&&req.method==='POST'){await readBody(req);dayClosing.pending_episodes=(dayClosing.pending_episodes||[]).filter(e=>e.id!==Number(episode[1]));send(res,200,{ok:true});return true;}
  const cash=path.match(/^\/api\/v1\/backstage\/pos\/cash\/(open|close|movement|drawer-open|change-request)\/$/);
  if(cash&&req.method==='POST') {
    const body=await readBody(req),key=body.client_request_id;
    if(key&&previewOnce.has(key)){send(res,200,previewOnce.get(key));return true;}
    const kind=cash[1];
    if(['open','close','movement','change-request'].includes(kind)) {
      const raw=body.amount??body.opening_amount??body.closing_amount;
      if(raw==null||raw===''||!Number.isFinite(Number(String(raw).replace(',','.')))||Number(String(raw).replace(',','.'))<0)return previewError(res,422,'Informe um valor válido.','amount');
    }
    if(kind==='open'){pos.cash_runtime.has_open_shift=true;pos.has_open_cash_session=true;cashReport.has_open_shift=true;cashReport.x_reading=clone(previewInitial.cashReport.x_reading);}
    if(kind==='close'){pos.cash_runtime.has_open_shift=false;pos.has_open_cash_session=false;cashReport.has_open_shift=false;const closed={...clone(cashReport.x_reading||previewInitial.cashReport.x_reading),status:'closed',closed_at:`${TODAY}T18:00:00-03:00`,counted_amount_display:String(body.closing_amount),notes:body.notes||''};cashReport.z_readings.push(closed);cashReport.x_reading=null;}
    if(kind==='movement'&&body.kind==='sangria'&&!previewManager(body,res))return true;
    if(kind==='movement')cashReport.x_reading.movements.push({entry_id:++previewSeq,kind:body.kind,kind_label:body.kind==='sangria'?'Saída de caixa':'Entrada de caixa',amount_q:Math.round(Number(String(body.amount).replace(',','.'))*100),amount_display:body.amount,reason:body.reason,created_by:'Ana',created_at:''});
    if(kind==='change-request')pos.cash_runtime.pending_change_requests.push({ref:`CR-${++previewSeq}`,amount_q:Math.round(Number(String(body.amount).replace(',','.'))*100),amount_display:brl(Math.round(Number(String(body.amount).replace(',','.'))*100)),denominations:body.denominations||[],requested_by:'Ana',note:body.note||'',requested_at:''});
    const response={ok:true,entry_id:++previewSeq};if(key)previewOnce.set(key,response);send(res,200,response);return true;
  }
  const change=path.match(/^\/api\/v1\/backstage\/pos\/cash\/change-request\/([^/]+)\/(serve|cancel)\/$/);
  if(change&&req.method==='POST'){const body=await readBody(req);if(change[2]==='serve'&&!previewManager(body,res))return true;pos.cash_runtime.pending_change_requests=pos.cash_runtime.pending_change_requests.filter(c=>c.ref!==change[1]);send(res,200,{ok:true});return true;}
  const refund=path.match(/^\/api\/v1\/backstage\/pos\/(cash\/refund|card-machine-refund)\/([^/]+)\/$/);
  if(refund&&req.method==='POST'){const body=await readBody(req);if(!previewManager(body,res))return true;const key=refund[1]==='cash/refund'?'pending_cash_refunds':'pending_card_machine_refunds';pos.cash_runtime[key]=pos.cash_runtime[key].filter(x=>x.order_ref!==refund[2]);send(res,200,{ok:true});return true;}
  const settle=path.match(/^\/api\/v1\/backstage\/pos\/accounts\/([^/]+)\/settle\/$/);
  if(settle&&req.method==='POST'){await readBody(req);pos.cash_runtime.account_balances=pos.cash_runtime.account_balances.filter(c=>c.customer_ref!==settle[1]);send(res,200,{ok:true});return true;}
  return false;
}
