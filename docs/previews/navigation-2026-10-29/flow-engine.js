/* Motor de composição da prévia. Sem backend, credenciais ou persistência. */
let activeFlow=null,activeFlowContext={},dialogBaseline='',dialogGuard=false,discardNext=null;
function flowButtons(ids){return ids.map(id=>{const f=FLOW_CATALOG.find(x=>x.id===id);return f?`<button class="button flow-link" data-flow="${id}">${icon(f.danger?'warning':'arrow')}<span>${esc(f.title)}</span></button>`:'';}).join('');}
const PAGE_FLOW_IDS=new Set(['catalog-bulk','receipt-remark','receipt-voucher','csv-import','csv-export']);
function pageFlowOptions(){const ids=FLOW_CATALOG.filter(f=>f.app===state.app&&f.view===state.view&&PAGE_FLOW_IDS.has(f.id)).map(f=>f.id);return ids.length?`<div class="flow-menu"><span class="option-heading">Ferramentas da página</span>${flowButtons(ids)}</div>`:'';}
function formFingerprint(){return JSON.stringify(Array.from(document.querySelectorAll('#detail input,#detail textarea,#detail select')).filter(e=>e.id!=='flow-section').map(e=>[e.name||e.id,e.type==='checkbox'?e.checked:e.value]));}
function trackDialog(){dialogGuard=['form','workspace'].includes(document.querySelector('#detail').dataset.kind);dialogBaseline=formFingerprint();}
function requestDialogClose(next=null){
 if(dialogGuard&&document.querySelector('#detail').open&&formFingerprint()!==dialogBaseline){discardNext=next;const d=document.querySelector('#discard-dialog');d.showModal();document.querySelector('#keep-editing').focus();return;}
 document.querySelector('#detail').close();if(next)next();
}
function flowField(label,index,type='text',value='',required=false){
 const name='flow-field-'+index,id=name;
 if(type==='checkbox')return `<label class="flow-check"><input id="${id}" name="${name}" type="checkbox" ${value?'checked':''}>${esc(label)}</label>`;
 const attributes=`id="${id}" name="${name}" data-flow-label="${esc(label)}" ${required?'required':''}`;
 return `<label class="field" for="${id}">${esc(label)}${required?' *':''}${type==='textarea'?`<textarea ${attributes} rows="3">${esc(value)}</textarea>`:`<input ${attributes} type="${type}" ${type==='number'?'min="0" step="0.01" inputmode="decimal"':''} value="${esc(value)}">`}<span class="field-error" id="${id}-error" hidden></span></label>`;
}
function inferredField(label,index){
 const isProduct=activeFlow.id==='product-editor',p=products.find(p=>p.id===activeFlowContext.id)||products[0];
 let value='',type=/Description|description/.test(label)?'textarea':'text',required=false;
 if(/Descrição|Observa|Ingredientes|Alérgenos|Restrições|Legenda/.test(label))type='textarea';
 if(/Preço|Valor pago|Limite da conta|Fator|Validade|Peso |Porção|Porções|energético|Carboidratos|Açúcares|Proteínas|Gorduras|Fibras|Sódio|Ciclo/.test(label))type='number';
 if(/Pode |Exibido|Disponível para|Ativo|preferencial|por padrão|Principal do/.test(label))type='checkbox';
 if(isProduct&&label==='Nome do produto'){value=activeFlowContext.create?'':p.name;required=true;}
 if(isProduct&&label==='Preço (R$)'){value=activeFlowContext.create?'':p.price/100;required=true;}
 if(label==='Nome'&&activeFlow.id==='customer-editor'){value=activeFlowContext.create?'':(activeFlowContext.name||'Ana Lima');required=true;}
 if(label==='Nome'&&activeFlow.id==='material-editor'){value=activeFlowContext.create?'':(activeFlowContext.name||'Farinha de trigo T65');required=true;}
 if(label==='SKU'){value=activeFlowContext.create?'':(activeFlowContext.id||'FAR-T65');required=true;}
 if(label==='Unidade-base')value='kg';
 if(label==='Razão social'){value=activeFlowContext.create?'':(activeFlowContext.name||'Moinho do Vale');required=true;}
 if(label==='Telefone')value='(43) 90000-0101';
 if(label==='Coleção')value=p.collection;
 if(type==='checkbox')value=/Ativo|Exibido|Disponível|Pode ser vendido/.test(label);
 if(label==='Data de nascimento')type='date';if(label==='E-mail'||label.startsWith('E-mail '))type='email';
 return flowField(label,index,type,value,required);
}
function showFlow(id,context={}){
 if(document.querySelector('#options-popover').matches(':popover-open'))document.querySelector('#options-popover').hidePopover();
 if(document.querySelector('#detail').open)document.querySelector('#detail').close();
 activeFlow=FLOW_CATALOG.find(f=>f.id===id);activeFlowContext=context;
 if(!activeFlow)return;
 const f=activeFlow,readOnly=f.kind==='detail';let index=0;
 const sections=f.sections||[];
 const chooser=sections.length?`<label class="flow-section-select">Seção<select id="flow-section">${sections.map((s,i)=>`<option value="${i}">${esc(s[0])}</option>`).join('')}</select></label>`:'';
 let body=(f.description?`<p class="flow-description">${esc(f.description)}</p>`:'')+chooser;
 if(f.facts)body+=f.facts.map(([label,value])=>`<div class="fact"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
 body+=sections.map(([title,labels],i)=>`<section data-flow-section="${i}" ${i?'hidden':''}><h3>${esc(title)}</h3>${readOnly?labels.map(label=>`<p>${esc(label)}</p>`).join(''):labels.map(label=>inferredField(label,index++)).join('')}</section>`).join('');
 if(f.fields)body+=f.fields.map(([label,type,value,required])=>flowField(label,index++,type,value,required)).join('');
 if(f.actions&&!context.create)body+=`<section class="flow-related"><h3>Mais funções</h3>${flowButtons(f.actions)}</section>`;
 const footer=readOnly?'':button('Cancelar','close')+`<button class="button ${f.danger?'danger':'gold'}" data-flow-save>${esc(f.confirm||'Salvar')}</button>`;
 openDialog(context.create&&['product-editor','customer-editor','material-editor','supplier-editor'].includes(id)?'Cadastrar '+(id==='product-editor'?'produto':id==='customer-editor'?'cliente':id==='material-editor'?'insumo':'fornecedor'):context.title||(id==='product-editor'&&context.id?products.find(p=>p.id===context.id)?.name:'')||(readOnly&&context.name)||f.title,body,footer,readOnly?(sections.length?'record':'detail'):sections.length?'workspace':f.fields?'form':'confirm');
 if(id==='product-editor'&&context.id){const list=catalogList(),at=list.findIndex(p=>p.id===context.id);document.querySelector('#detail .dialog-foot').insertAdjacentHTML('afterbegin',`<nav class="record-pagination" aria-label="Produtos deste recorte"><button class="icon-button" data-flow-step="-1" aria-label="Produto anterior" ${at<=0?'disabled':''}>${icon('left')}</button><span>${at+1} de ${list.length}</span><button class="icon-button" data-flow-step="1" aria-label="Próximo produto" ${at===list.length-1?'disabled':''}>${icon('arrow')}</button></nav>`);}
 document.querySelector('#detail').dataset.flowId=id;
 trackDialog();
}
function validateFlow(){
 let invalid=null;
 document.querySelectorAll('#detail [data-flow-label]').forEach(input=>{
  const label=input.dataset.flowLabel,number=input.type==='number'&&input.value!==''?Number(input.value):null;
  const missing=input.required&&!input.value.trim();
  const badNumber=input.type==='number'&&input.value!==''&&(!Number.isFinite(number)||number<0||(/Preço|Valor pago/.test(label)&&number<=0));
  const badKey=label.includes('44 dígitos')&&input.value.replace(/\D/g,'').length!==44;
  const error=missing?'Preencha '+label.toLocaleLowerCase('pt-BR')+'.':badNumber?'Informe um valor válido para '+label.toLocaleLowerCase('pt-BR')+'.':badKey?'A chave precisa ter 44 dígitos.':'';
  const target=document.getElementById(input.id+'-error');target.textContent=error;target.hidden=!error;
  input.setAttribute('aria-invalid',String(Boolean(error)));if(error)input.setAttribute('aria-describedby',target.id);else input.removeAttribute('aria-describedby');
  if(error&&!invalid)invalid=input;
 });
 if(invalid){const section=invalid.closest('[data-flow-section]');if(section){document.getElementById('flow-section').value=section.dataset.flowSection;document.querySelectorAll('[data-flow-section]').forEach(s=>s.hidden=s!==section);}toast('Revise os campos indicados. Seu rascunho foi mantido.','error');invalid.focus();return false;}
 return true;
}
function commitFlow(){
 if(!validateFlow())return;
 const scenario=new URLSearchParams(location.search).get('scenario');
 if(['offline','error','conflict'].includes(scenario)){toast(scenario==='conflict'?'O registro foi atualizado por outra pessoa. Seu rascunho foi mantido para comparação.':scenario==='offline'?'Sem conexão. Seu rascunho foi mantido. Tente novamente quando a conexão voltar.':'Não foi possível salvar. Seu rascunho foi mantido. Tente novamente.','error');return;}
 if(activeFlow.id==='product-editor'){
  const fields=[...document.querySelectorAll('#detail [data-flow-label]')],name=fields.find(e=>e.dataset.flowLabel==='Nome do produto').value,price=Number(fields.find(e=>e.dataset.flowLabel==='Preço (R$)').value);
  const p=products.find(p=>p.id===activeFlowContext.id);if(p){p.name=name;p.price=Math.round(price*100);}
 }
 const f=activeFlow;
 if(f.confirm){const d=document.querySelector('#action-confirm');document.querySelector('#action-confirm-title').textContent=f.title;document.querySelector('#action-confirm-description').textContent=f.description||'Confirme os dados revisados. Esta ação altera somente a amostra local.';const act=document.querySelector('#action-confirm-act');act.textContent=f.confirm;act.className='button '+(f.danger?'danger':'gold');d.showModal();document.querySelector('#action-confirm-back').focus();return;}
 finishFlow();
}
function finishFlow(){if(activeFlow.id==='merge-undo')state.mergeUndone=true;if(activeFlow.id==='routine-evidence')state.done.add(activeFlowContext.taskIndex??0);document.querySelector('#action-confirm').close();document.querySelector('#detail').close();dialogGuard=false;renderContent();renderHead();toast('Operação concluída na amostra local.');}
function interceptPreviewFlow(name,id){
 const map={'new-group':['group-edit',{create:true}],'new-product':['product-editor',{create:true}],'product':['product-editor',{id}],'catalog-grid':['catalog-bulk',{}],'new-customer':['customer-editor',{create:true}],'new-material':['material-editor',{create:true}],'new-supplier':['supplier-editor',{create:true}],'group':['group-edit',{title:'Grupo '+id}],'merge':['merge-customers',{}],'simulate-merge':['merge-customers',{}],'station':['station-edit',{title:'Posto '+id}],'replenish':['purchase-send',{id}],'scan':['receipt-start',{}],'channel':['channel-detail',{}]};
 if(name==='customer'){showFlow('customer-detail',{name:customers[Number(id)]?.name});return true;}
 if(name==='order'){const o=orders.find(o=>o.ref===id);openDialog('Pedido '+id,`<div class="fact"><span>Cliente</span><strong>${esc(o.name)}</strong></div><p>${esc(o.items)}</p><div class="fact"><span>Canal</span><strong>${o.channel}</strong></div><div class="fact"><span>Atendimento</span><strong>${o.delivery}</strong></div><div class="fact"><span>Total</span><strong>${money(o.total)}</strong></div><section class="flow-related"><h3>Atendimento</h3>${flowButtons(o.stage===2?[o.delivery==='Entrega'?'dispatch':'order-pickup','courier-return']:['order-advance','order-reject'])}<h3>Acompanhamento</h3>${flowButtons(['kitchen-note','order-payment','ombudsman','order-undo'])}</section>`,'','detail');return true;}
 if(name==='historical'){showFlow('order-payment',{title:'Pedido '+id});return true;}
 if(name==='material'){const m=materials.find(m=>m.id===id);activeFlowContext={id:m.id,name:m.name};openDialog(m.name,`<div class="fact"><span>SKU</span><strong>${m.id}</strong></div><div class="fact"><span>Unidade</span><strong>${m.unit}</strong></div><div class="fact"><span>Saldo</span><strong>${m.stock} ${m.unit}</strong></div><div class="fact"><span>Fornecedor</span><strong>${m.supplier}</strong></div><section class="flow-related"><h3>Cadastro e compra</h3>${flowButtons(['material-editor','cost-quote','material-minimum','material-opening','material-duplicate','permit-resale'])}${m.id==='GEL'?button('Abrir produto no Gestor','cross-material','link'):''}</section>`,'','detail');return true;}
 if(name==='supplier'){const name=['Moinho do Vale','Laticínios da Serra','Distribuidora Aurora'][Number(id)];activeFlowContext={name};openDialog(name,`<div class="fact"><span>Contato comercial</span><strong>(43) 90000-0200</strong></div><div class="fact"><span>Prazo de entrega</span><strong>2 dias</strong></div><section class="flow-related"><h3>Fornecedor</h3>${flowButtons(['supplier-editor','supplier-duplicate','cost-quote'])}</section>`,'','detail');return true;}
 if(map[name]){showFlow(...map[name]);return true;}return false;
}
function renderPreviewScenario(){
 const scenario=new URLSearchParams(location.search).get('scenario')||'ready';
 if(scenario==='ready')return;
 if(['offline','conflict'].includes(scenario)){document.querySelector('#content').insertAdjacentHTML('afterbegin',`<div class="semantic-alert ${scenario==='offline'?'warning':'error'}"><span>${scenario==='offline'?'Sem conexão. Os últimos dados continuam visíveis; alterações aguardam conexão.':'Dados atualizados por outra pessoa. Confira a versão atual antes de salvar.'}</span><button class="button" data-review-state="ready">${scenario==='offline'?'Tentar reconectar':'Recarregar dados'}</button></div>`);return;}
 document.querySelector('#support-top').hidden=true;document.querySelector('#support-bottom').hidden=true;document.querySelector('#action-dock').hidden=true;
 const messages={loading:['Carregando','Aguarde os dados desta página.'],empty:['Nenhum registro neste recorte','Limpe os filtros ou cadastre um registro quando aplicável.'],error:['Não foi possível carregar','Você pode tentar novamente sem sair desta página.'],forbidden:['Acesso não autorizado','Esta função depende da permissão do operador.']};const m=messages[scenario]||messages.error;
 document.querySelector('#content').innerHTML=`<section class="preview-screen-state"><span class="list-icon">${icon(scenario==='loading'?'clock':scenario==='forbidden'?'lock':scenario==='empty'?'box':'warning')}</span><h2>${m[0]}</h2><p>${m[1]}</p>${scenario==='loading'?'<div class="skeleton-row"></div><div class="skeleton-row"></div>':''}${scenario==='forbidden'?'<button class="button" data-action="central">Voltar à Central</button>':`<button class="button gold" data-review-state="ready">${scenario==='error'?'Tentar novamente':scenario==='empty'?'Limpar filtros':'Mostrar dados'}</button>`}</section>`;
 document.querySelector('.page-actions').hidden=['forbidden','loading','error'].includes(scenario);
 if(scenario==='error')document.querySelector('#content').innerHTML=`<div class="semantic-alert error" role="alert"><span>Não foi possível carregar os dados desta página.</span><button class="button alert-action" data-review-state="ready">Tentar novamente</button></div>`;
}
document.addEventListener('click',event=>{
 const flow=event.target.closest('[data-flow]');if(flow){event.preventDefault();const context=flow.dataset.taskIndex!==undefined?{taskIndex:Number(flow.dataset.taskIndex)}:flow.closest('#options-popover')?{}:activeFlowContext;const next=()=>showFlow(flow.dataset.flow,context);if(document.querySelector('#detail').open)requestDialogClose(next);else next();return;}
 if(event.target.closest('[data-flow-save]')){commitFlow();return;}
 const step=event.target.closest('[data-flow-step]');if(step){const list=catalogList(),index=list.findIndex(p=>p.id===activeFlowContext.id),p=list[index+Number(step.dataset.flowStep)];if(p)requestDialogClose(()=>showFlow('product-editor',{id:p.id}));return;}
 if(event.target.closest('#keep-editing')){document.querySelector('#discard-dialog').close();return;}
 if(event.target.closest('#discard-editing')){document.querySelector('#discard-dialog').close();dialogGuard=false;document.querySelector('#detail').close();const next=discardNext;discardNext=null;if(next)next();return;}
 if(event.target.closest('#action-confirm-back')){document.querySelector('#action-confirm').close();return;}
 if(event.target.closest('#action-confirm-act')){finishFlow();return;}
 const scenario=event.target.closest('[data-review-state]');if(scenario){const url=new URL(location.href);url.searchParams.delete('scenario');history.replaceState(null,'',url);state.search='';state.filter='all';state.collection='all';render();}
});
document.addEventListener('change',event=>{
 if(event.target.id==='flow-section')document.querySelectorAll('[data-flow-section]').forEach(s=>s.hidden=s.dataset.flowSection!==event.target.value);
 if(event.target.id==='review-state'){const url=new URL(location.href);if(event.target.value==='ready')url.searchParams.delete('scenario');else url.searchParams.set('scenario',event.target.value);history.replaceState(null,'',url);render();}
});
function countStatus(m){
 if(state.counted[m.id]===undefined)return tag('A contar');
 const difference=state.counted[m.id]-m.stock;
 return tag(difference===0?'Confere':(difference>0?'+':'')+number(difference)+' '+m.unit,difference===0?'green':difference<0?'red':'amber')+(difference?`<label class="count-reason-label">Motivo da divergência<input class="row-input" data-count-reason="${m.id}" aria-label="Motivo da divergência de ${esc(m.name)}" value="${esc(state.countReasons[m.id]||'')}" placeholder="Por que divergiu?"></label>`:'');
}
function showCountReview(){
 const chosen=materials.filter(m=>state.counted[m.id]!==undefined);
 const missing=chosen.find(m=>state.counted[m.id]!==m.stock&&!state.countReasons[m.id]?.trim());
 if(missing){toast('Informe o motivo da divergência de '+missing.name+'.','error');document.querySelector(`[data-count-reason="${missing.id}"]`)?.focus();return;}
 showFlow('count-review');document.querySelector('#detail .dialog-body').innerHTML=chosen.map(m=>`<div class="fact"><span>${esc(m.name)}</span><strong>${state.counted[m.id]} ${m.unit}</strong></div><p class="subtle">Sistema: ${m.stock} ${m.unit}${state.countReasons[m.id]?' · '+esc(state.countReasons[m.id]):''}</p>`).join('');trackDialog();
}
