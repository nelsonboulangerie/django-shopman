/* Prévia de interação isolada. Somente dados fictícios e estado em memória. */
'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = q => (q / 100).toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
const number = n => Number(n).toLocaleString('pt-BR');
const paths = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  orders:'<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 9h6M9 13h6M9 17h4"/>',
  box:'<path d="m3 7 9-5 9 5v10l-9 5-9-5V7ZM3 7l9 5 9-5M12 12v10M7.5 4.5l9 5"/>',
  users:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5v2"/>',
  channels:'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 21h8M12 16v5M7 9h2M11 9h6M7 12h10"/>',
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="16" cy="17" r="3" fill="currentColor" stroke="none"/>',
  cart:'<path d="M2 3h3l3 12h11l3-9H6M8 15l-1 3h13"/><circle cx="9" cy="21" r="1"/><circle cx="18" cy="21" r="1"/>',
  truck:'<path d="M2 5h12v12H2zM14 9h4l4 4v4h-8"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/>',
  arrow:'<path d="m9 5 7 7-7 7"/>',
  left:'<path d="m14 5-7 7 7 7"/>',
  down:'<path d="m6 9 6 6 6-6"/>',
  panel:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18m5-13-3 4 3 4"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  bell:'<path d="M5 17h14l-2-4V9a5 5 0 0 0-10 0v4l-2 4ZM10 21h4"/>',
  plus:'<path d="M12 4v16M4 12h16"/>',
  check:'<path d="m5 12 4 4L20 5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  bread:'<path d="M6 20C0 19 5 9 11 5s12-3 10 3S12 21 6 20Z"/><path d="m9 8 4 3m0-6 4 3m-12 4 4 3"/>',
  leaf:'<path d="M4 20C2 8 9 3 21 3c0 13-6 18-14 14M4 20l11-11"/>',
  warning:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17v.1"/>',
  file:'<path d="M5 2h10l5 5v15H5V2ZM15 2v6h5M9 12h7M9 16h7"/>',
  coins:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 4 16 4 16 0V6M4 12v6c0 4 16 4 16 0v-6"/>',
  scale:'<path d="M12 3v18M5 21h14M3 7h18M5 7l-4 8h8L5 7ZM19 7l-4 8h8l-4-8Z"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  history:'<path d="M3 11a9 9 0 1 1 3 8M3 4v7h7M12 7v5l3 2"/>',
  tag:'<path d="M3 3h9l10 10-9 9L3 12V3Z"/><circle cx="8" cy="8" r="1"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
  compare:'<rect x="2" y="4" width="8" height="16" rx="1.5"/><rect x="14" y="4" width="8" height="16" rx="1.5"/>',
  link:'<path d="m9 15 6-6M8 16l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const tag = (label, tone = '', dot = false) => `<span class="tag ${tone} ${dot?'dot':''}">${esc(label)}</span>`;
const button = (label, action, symbol = '', kind = '') => `<button type="button" class="button ${kind}" data-action="${esc(action)}">${symbol?icon(symbol):''}${esc(label)}</button>`;
const navLink = (label, view, symbol = '', count = '', extra = '') => `<a class="navitem ${state.view===view?'active':''} ${extra}" href="${href({view,compare:false})}" data-view="${view}" ${state.view===view?'aria-current="page"':''}>${symbol?icon(symbol):''}<span class="navlabel">${esc(label)}</span>${count?`<span class="navcount">${count}</span>`:''}</a>`;

const applications = {
  gestor:{label:'Gestor',symbol:'orders',home:'queue',groups:[
    {id:'orders',label:'Pedidos',symbol:'orders',count:8,description:'Da entrada até a entrega.',children:[['queue','Em andamento','orders','8'],['exit','Saída','truck','3'],['history','Histórico','history']]},
    {id:'products',label:'Produtos',symbol:'box',description:'O que a casa vende e como apresenta.',children:[['catalog','Catálogo','box'],['collections','Coleções','grid']]},
    {id:'customers',label:'Clientes',symbol:'users',description:'Cadastro e relações comerciais.',children:[['customers','Cadastro','users'],['groups','Grupos','tag'],['merges','Unificações','users','1']]},
    {id:'channels',label:'Canais',symbol:'channels',description:'Por onde vendemos e o que aparece.',children:[['channels','Canais de venda','channels'],['channel-catalog','Catálogo por canal','grid']]},
    {id:'operation',label:'Operação',symbol:'settings',description:'Rotinas da casa e postos de trabalho.',children:[['routines','Rotinas','check'],['stations','Postos','grid']]},
  ]},
  compras:{label:'Compras',symbol:'cart',home:'overview',groups:[
    {id:'overview',label:'Visão geral',symbol:'grid',description:'O que precisa de atenção hoje.',children:[['overview','Visão geral','grid']]},
    {id:'purchasing',label:'Compras',symbol:'cart',description:'Repor, escolher fornecedor e conferir custo.',children:[['replenishment','Reposição','cart','2'],['suppliers','Fornecedores','truck'],['costs','Custos de compra','coins']]},
    {id:'receipts',label:'Recebimentos',symbol:'truck',count:1,description:'Conferir o que chegou antes de dar entrada.',children:[['receiving','Conferência','file'],['divergences','Divergências','warning','1']]},
    {id:'stock',label:'Estoque',symbol:'box',description:'Conhecer os insumos e conferir o saldo físico.',children:[['materials','Insumos','box'],['count','Contagem','check']]},
  ]},
};
const viewInfo = {
  queue:['Em andamento','Acompanhe a entrada, o preparo e a saída dos pedidos.'],
  exit:['Saída','Pedidos prontos para retirar ou despachar.'],
  history:['Histórico de pedidos','Consulte pedidos concluídos e seus acontecimentos.'],
  catalog:['Catálogo','Produtos, preços e organização da vitrine.'],
  collections:['Coleções','Organize como os produtos são apresentados ao cliente.'],
  customers:['Clientes','Um cadastro por pessoa, com seu histórico e grupo.'],
  groups:['Grupos de clientes','As condições comerciais de cada grupo.'],
  merges:['Unificações','Revise possíveis cadastros da mesma pessoa.'],
  channels:['Canais de venda','Acompanhe a operação de cada porta de entrada.'],
  'channel-catalog':['Catálogo por canal','Confira onde cada produto pode ser vendido.'],
  routines:['Rotinas da loja','O que precisa ser feito, por quem e até quando.'],
  stations:['Postos de trabalho','Onde os dispositivos ficam e qual trabalho atendem.'],
  overview:['Visão geral','As prioridades de hoje, da reposição ao recebimento.'],
  replenishment:['Reposição','O que comprar para sustentar os próximos dias.'],
  suppliers:['Fornecedores','Contatos e insumos oferecidos por cada fornecedor.'],
  costs:['Custos de compra','Compare custos na unidade de estoque do insumo.'],
  receiving:['Conferência de recebimento','Confira os itens e resolva as diferenças antes da entrada.'],
  divergences:['Divergências no recebimento','As diferenças que precisam de uma decisão na conferência.'],
  materials:['Insumos','Cadastro, unidade e saldo de cada insumo.'],
  count:['Contagem de estoque','Registre a quantidade encontrada sem consultar o saldo esperado.'],
};
const products = [
  {id:'BGT',name:'Baguette de Tradition',collection:'Pães de fermentação natural',price:1800,stock:24,tone:'green',status:'À venda',icon:'bread'},
  {id:'CRO',name:'Croissant',collection:'Viennoiseries',price:1300,stock:8,tone:'green',status:'À venda',icon:'bread'},
  {id:'PAC',name:'Pain au Chocolat',collection:'Viennoiseries',price:1550,stock:0,tone:'amber',status:'Esgotado',icon:'bread'},
  {id:'CAF',name:'Cappuccino',collection:'Cafés e bebidas',price:1200,stock:null,tone:'green',status:'À venda',icon:'coins'},
  {id:'GEL',name:'Geleia de frutas vermelhas',collection:'Mercearia',price:3200,stock:12,tone:'green',status:'À venda',icon:'leaf'},
  {id:'PNI',name:'Pão integral',collection:'Pães de fermentação natural',price:2600,stock:6,tone:'',status:'Pausado',icon:'bread'},
];
const materials = [
  {id:'FAR-T65',name:'Farinha de trigo T65',stock:18,unit:'kg',coverage:'Menos de 1 dia',supplier:'Moinho do Vale',cost:480,suggestion:'4 sacos de 25 kg',urgent:true},
  {id:'MAN-82',name:'Manteiga sem sal 82%',stock:9,unit:'kg',coverage:'1,2 dia',supplier:'Laticínios da Serra',cost:7800,suggestion:'10 kg',urgent:true},
  {id:'ACU-REF',name:'Açúcar refinado',stock:48,unit:'kg',coverage:'4,1 dias',supplier:'Distribuidora Aurora',cost:650,suggestion:'8 kg',urgent:false},
  {id:'CHO-70',name:'Chocolate 70%',stock:12,unit:'kg',coverage:'6 dias',supplier:'Distribuidora Aurora',cost:9600,suggestion:'Não precisa repor',urgent:false},
  {id:'SAL',name:'Sal marinho',stock:16,unit:'kg',coverage:'12 dias',supplier:'Distribuidora Aurora',cost:390,suggestion:'Não precisa repor',urgent:false},
  {id:'GEL',name:'Geleia de frutas vermelhas',stock:12,unit:'un.',coverage:'8 dias',supplier:'Distribuidora Aurora',cost:1800,suggestion:'Não precisa repor',urgent:false},
];
const customers = [{name:'Ana Lima',phone:'(43) 90000-0101',group:'Varejo',orders:12},{name:'Rafael Costa',phone:'(43) 90000-0102',group:'Varejo',orders:4},{name:'Café da Praça',phone:'(43) 90000-0103',group:'Atacado',orders:28}];
const orders = [
  {ref:'N104',name:'Ana Lima',items:'2 Croissants · 1 Cappuccino',channel:'Loja online',delivery:'Retirada',time:'3 min',total:3800,stage:0},
  {ref:'N105',name:'Rafael Costa',items:'2 Baguettes · 1 Geleia',channel:'iFood',delivery:'Entrega',time:'1 min',total:6800,stage:0},
  {ref:'N106',name:'Luiza Martins',items:'1 Baguette · 2 Croissants',channel:'Loja online',delivery:'Retirada às 15h',time:'Agora',total:4400,stage:0},
  {ref:'N102',name:'Marina Alves',items:'2 Cappuccinos · 2 Croissants',channel:'PDV',delivery:'Mesa 04',time:'12 min',total:5000,stage:1},
  {ref:'N103',name:'Pedro Santos',items:'1 Baguette · 1 Cappuccino',channel:'iFood',delivery:'Entrega',time:'8 min',total:3000,stage:1},
  {ref:'N099',name:'Camila Rocha',items:'3 Baguettes · 2 Geleias',channel:'Loja online',delivery:'Retirada',time:'24 min',total:11800,stage:2},
  {ref:'N100',name:'Bruno Almeida',items:'2 Croissants · 2 Cappuccinos',channel:'iFood',delivery:'Entrega',time:'19 min',total:5000,stage:2},
  {ref:'N101',name:'Isabela Melo',items:'1 Pão integral · 1 Geleia',channel:'Loja online',delivery:'Retirada',time:'15 min',total:5800,stage:2},
];
const receipt = [
  {id:'farinha',name:'Farinha de trigo T65',sku:'FAR-T65',expected:4,received:4,unit:'sacos de 25 kg',cost:12000,resolved:true},
  {id:'manteiga',name:'Manteiga sem sal 82%',sku:'MAN-82',expected:10,received:8,unit:'kg',cost:7800,resolved:false},
  {id:'acucar',name:'Açúcar refinado',sku:'ACU-REF',expected:8,received:8,unit:'kg',cost:650,resolved:true},
];
const params = new URLSearchParams(location.search);
const state = {
  app:params.get('app')==='compras'?'compras':'gestor',
  variant:params.get('variant')==='double'?'double':'single',
  view:params.get('view') || (params.get('app')==='compras'?'receiving':'catalog'),
  compact:params.get('compact')==='1'||matchMedia('(min-width:651px) and (max-width:1100px) and (orientation:landscape)').matches,hidden:false,secondary:true,
  embedded:params.get('embedded')==='1',compare:params.get('compare')==='1',
  drawer:false,drawerGroup:null,central:params.get('screen')==='central',trail:null,lastViews:{gestor:'catalog',compras:'receiving'},search:'',filter:'all',closed:new Set(),done:new Set(),counted:{},
};
if (!applications[state.app].groups.some(g=>g.children.some(c=>c[0]===state.view))) state.view=applications[state.app].home;
state.lastViews[state.app]=state.view;
state.closed=new Set(applications[state.app].groups.filter(g=>!g.children.some(c=>c[0]===state.view)).map(g=>g.id));
let previousFocus=null, toastTimer=null;
function renderMobileGroup(){const group=applications[state.app].groups.find(g=>g.id===state.drawerGroup);return `<button class="drawer-back" data-action="drawer-back">${icon('left')}Todos os assuntos</button><div class="drawer-topic"><strong>${group.label}</strong><p>${group.description}</p></div>${group.children.map(c=>navLink(c[1],c[0],c[2],c[3]||'')).join('')}`;}
function renderQuick(){const groups=applications[state.app].groups;const shown=state.app==='gestor'?groups.slice(0,3):groups;$('#quicknav').hidden=state.compare||state.central;$('#quicknav').innerHTML=shown.map(g=>`<button data-quick-group="${g.id}" class="${g.id===currentGroup().id?'active':''}" ${g.id===currentGroup().id?'aria-current="true"':''}>${icon(g.symbol)}<span>${g.label==='Visão geral'?'Visão geral':g.label}</span></button>`).join('')+(state.app==='gestor'?`<button data-action="drawer">${icon('menu')}<span>Mais</span></button>`:'');}
function renderCentral(){const items=[['gestor','Gestor','Pedidos, produtos, clientes e operação','orders'],['compras','Compras','Reposição, recebimentos e estoque','cart']];$('#central').innerHTML=`<header class="central-head"><span class="central-mark">s</span><div><p class="section-label">Shopman · Loja exemplo</p><h1>Central de apps</h1><p>Olá, Maria. Por onde vamos continuar?</p></div><button class="button" data-action="resume">${icon('left')}Voltar a ${applications[state.app].label}</button></header><div class="central-body"><section class="panel"><div class="panel-head"><div><h2>Precisa de você</h2><p>Abra a tarefa no contexto certo.</p></div>${tag('2 tarefas','amber')}</div><div class="list-row"><span class="list-icon">${icon('truck')}</span><div><strong>A retirada N099 está esperando</strong><small>Gestor · Saída dos pedidos</small></div><button class="text-link end" data-action="jump:gestor:exit">Ver saída ${icon('arrow')}</button></div><div class="list-row"><span class="list-icon">${icon('warning')}</span><div><strong>Uma diferença na nota 004821</strong><small>Compras · Conferência de recebimento</small></div><button class="text-link end" data-action="jump:compras:divergences">Conferir ${icon('arrow')}</button></div></section><h2 class="central-section">Seus apps</h2><div class="central-apps">${items.map(a=>`<button class="central-app-card" data-app="${a[0]}"><span class="list-icon">${icon(a[3])}</span><strong>${a[1]}</strong><p>${a[2]}</p><span class="text-link">Continuar de onde parou ${icon('arrow')}</span></button>`).join('')}</div><p class="subtle">Esta rodada permite explorar Gestor e Compras. Os demais apps continuam fora da prévia.</p></div>`;}
function crossApp(app,view,query,label,dialog){state.trail={app:state.app,view:state.view,search:state.search,label,dialog};if($('#detail').open)$('#detail').close();state.lastViews[state.app]=state.view;state.app=app;route(view);state.search=query;renderContent();renderHead();}
function currentGroup(){return applications[state.app].groups.find(g=>g.children.some(c=>c[0]===state.view));}
function href(overrides={}){
  const next={app:state.app,variant:state.variant,view:state.view,compare:state.compare,embedded:state.embedded,central:state.central,...overrides};
  const q=new URLSearchParams({app:next.app,variant:next.variant,view:next.view});
  if(next.compare)q.set('compare','1');if(next.embedded)q.set('embedded','1');if(next.central)q.set('screen','central');
  return `?${q}`;
}
function route(view, notify=true){
  if(!applications[state.app].groups.some(g=>g.children.some(c=>c[0]===view)))return;
  state.central=false;state.view=view;state.search='';state.filter='all';state.drawer=false;state.drawerGroup=null;state.lastViews[state.app]=view;
  state.closed=new Set(applications[state.app].groups.filter(g=>g.id!==currentGroup().id).map(g=>g.id));
  if(state.compare&&$$('#comparison iframe').length){$('#compare-destination').value=view;$$('#comparison iframe').forEach(f=>f.contentWindow.postMessage({type:'shopman-preview-set-route',view},location.origin));history.replaceState(null,'',href());return;}
  render();history[notify?'pushState':'replaceState'](null,'',href());
  if(state.embedded&&notify)parent.postMessage({type:'shopman-preview-route',app:state.app,view:state.view},location.origin);
}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4000);}
function renderLab(){
  $('#lab').innerHTML=`<div class="lab-brand"><span class="mark">s</span><div class="lab-title">Shopman <small>Estudo de navegação</small></div></div><div class="segments" aria-label="Aplicativo"><button data-app="gestor" aria-pressed="${state.app==='gestor'}">Gestor</button><button data-app="compras" aria-pressed="${state.app==='compras'}">Compras</button></div><span class="preview-tag">Prévia local · dados fictícios</span><div class="segments variant" aria-label="Modelo de navegação"><button data-variant="single" aria-pressed="${state.variant==='single'&&!state.compare}">A · Lateral única</button><button data-variant="double" aria-pressed="${state.variant==='double'&&!state.compare}">B · Dois níveis</button></div><button class="button compare ${state.compare?'active':''}" data-action="compare">${icon('compare')}Comparar</button><button class="icon-button" data-action="map" aria-label="Ver organização por assuntos">${icon('grid')}</button>`;
}
function renderNavigation(){
  const app=applications[state.app],group=currentGroup();
  const isTree=state.variant==='single';
  const tree=app.groups.map(g=>{
    if(g.children.length===1)return navLink(g.label,g.children[0][0],g.symbol);
    const closed=state.closed.has(g.id);
    return `<section class="navgroup"><button class="group-title ${g.id===group.id?'is-current':''}" data-group-toggle="${g.id}" aria-expanded="${!closed}" aria-controls="group-${g.id}">${icon(g.symbol)}<span>${g.label}</span>${icon('down').replace('<svg ','<svg class="caret" ')}</button><div id="group-${g.id}" ${closed?'hidden':''}>${g.children.map(c=>navLink(c[1],c[0],'',c[3]||'','indent')).join('')}</div></section>`;
  }).join('');
  const primary=app.groups.map(g=>`<a class="navitem ${g.id===group.id?'active':''}" href="${href({view:g.children[0][0],compare:false})}" data-view="${g.children[0][0]}" ${g.id===group.id?'aria-current="true"':''}>${icon(g.symbol)}<span class="navlabel">${g.label}</span>${g.count?`<span class="navcount">${g.count}</span>`:''}</a>`).join('');
  const drawerContent=state.drawer&&state.variant==='double'?(state.drawerGroup?renderMobileGroup():`<div class="nav-caption">Escolha um assunto</div>${app.groups.map(g=>`<button class="mobile-subject" data-drawer-group="${g.id}">${icon(g.symbol)}<span><strong>${g.label}</strong><small>${g.description}</small></span>${icon('arrow')}</button>`).join('')}`):null;
  $('#primary').innerHTML=`<div class="brand-row"><span class="app-logo">${icon(app.symbol)}</span><div class="brand-copy"><strong>${app.label}</strong><small>Loja exemplo</small></div><button class="primary-toggle" data-action="compact" aria-label="${state.drawer?'Fechar navegação':'Compactar barra principal'}">${icon(state.drawer?'close':'panel')}</button></div><div class="nav-scroll"><div class="nav-caption">${isTree?'Assuntos e tarefas':'Assuntos'}</div>${drawerContent??(isTree?tree:primary)}</div><div class="nav-footer"><button class="utility" data-action="apps">${icon('grid')}<span>Central e outros apps</span></button><button class="utility" data-action="alerts">${icon('bell')}<span>Avisos</span><span class="navcount">3</span></button><div class="profile"><span class="avatar">ML</span><div class="profile-text">Maria Lopes<small>Gestão da loja</small></div></div></div>`;
  const showSecondary=state.variant==='double'&&group.children.length>1&&state.secondary;
  $('#secondary').hidden=!showSecondary;
  $('#secondary').innerHTML=showSecondary?`<div class="secondary-top"><strong>${group.label}</strong><button data-action="secondary" aria-label="Recolher opções de ${group.label}">${icon('panel')}</button></div><nav class="nav-scroll" aria-label="Destinos de ${group.label}">${group.children.map(c=>navLink(c[1],c[0],c[2],c[3]||'')).join('')}</nav><div class="secondary-note">${icon(group.symbol)}${group.description}</div>`:'';
  $('#app').dataset.variant=state.variant;$('#app').dataset.compact=String(state.compact);$('#app').dataset.hidden=String(state.hidden);$('#app').dataset.drawer=String(state.drawer);$('#scrim').hidden=!state.drawer;$('#workspace').inert=state.drawer;$('#lab').inert=state.drawer;$('#quicknav').inert=state.drawer;$('#primary').setAttribute('role',state.drawer?'dialog':'complementary');if(state.drawer)$('#primary').setAttribute('aria-modal','true');else $('#primary').removeAttribute('aria-modal');
}
function pageActions(){
  const v=state.view;
  if(v==='catalog')return button('Tabelão','catalog-grid','grid')+button('Novo produto','new-product','plus','gold');
  if(v==='collections')return button('Nova coleção','new-collection','plus','gold');
  if(v==='customers')return button('Novo cliente','new-customer','plus','gold');
  if(v==='suppliers')return button('Novo fornecedor','new-supplier','plus','gold');
  if(v==='materials')return button('Novo insumo','new-material','plus','gold');
  if(v==='receiving')return button('Ler outra nota','scan','file');
  if(v==='replenishment')return button('Rever critérios','criteria','settings');
  if(v==='count')return button('Concluir contagem','finish-count','check','gold');
  return '';
}
function renderHead(){
  const group=currentGroup(),app=applications[state.app],info=viewInfo[state.view];
  const secondaryControl=state.variant==='double'&&group.children.length>1?`<button class="pill-button desktop-control" data-action="secondary" aria-label="${state.secondary?'Recolher':'Mostrar'} opções de ${group.label}">${icon('panel')}${state.secondary?'Recolher opções':`Opções de ${group.label}`}</button>`:'';
  $('#pagehead').innerHTML=`<div class="head-top"><button class="icon-button mobile-menu" data-action="drawer" aria-label="Abrir navegação">${icon('menu')}</button><button class="icon-button desktop-control" data-action="compact" aria-label="${state.compact?'Expandir':'Compactar'} barra principal">${icon('panel')}</button><button class="app-switch" data-action="apps" aria-label="${app.label}: trocar app ou voltar à Central">${icon(app.symbol)}<span>${app.label}</span>${icon('down')}</button><div class="breadcrumb"><span class="desktop-breadcrumb">${app.label}</span>${icon('arrow')}<span>${group.label}</span>${group.children.length>1?icon('arrow')+`<span>${group.children.find(c=>c[0]===state.view)[1]}</span>`:''}</div><div class="head-spacer"></div><div class="head-utility">${secondaryControl}<button class="icon-button desktop-control" data-action="hide" aria-label="${state.hidden?'Mostrar':'Ocultar'} barra principal">${icon('menu')}</button><button class="icon-button" data-action="search-suite" aria-label="Buscar na suíte">${icon('search')}</button></div></div><div class="heading-row"><div><h1>${info[0]}</h1><p>${info[1]}</p></div><div class="page-actions">${pageActions()}</div></div>${state.trail?`<div class="return-context"><button data-action="return-context">${icon('left')}Voltar a ${esc(state.trail.label)}</button><span>Contexto de origem preservado</span></div>`:''}${group.children.length>1?`<div class="context-switch"><button class="button" data-action="context-mobile">${icon(group.symbol)}${group.label} · ${group.children.find(c=>c[0]===state.view)[1]} ${icon('down')}</button></div>`:''}`;
}
const kpi=(label,value,note,symbol='grid',attention=false)=>`<div class="kpi ${attention?'attention':''}"><div class="kpi-label">${icon(symbol)}${label}</div><div class="kpi-value">${value}</div><p>${note}</p></div>`;
const search=(placeholder)=>`<label class="search">${icon('search')}<input type="search" data-search-input placeholder="${placeholder}" aria-label="${placeholder}" value="${esc(state.search)}"></label>`;
const toolbar=(placeholder,extra='')=>`<div class="toolbar">${search(placeholder)}${extra}</div>`;
const filterButton=(label,key)=>`<button class="filter-chip ${state.filter===key?'active':''}" data-filter="${key}" aria-pressed="${state.filter===key}">${label}</button>`;
const table=(heads,rows,label)=>`<div class="table-scroll"><table aria-label="${esc(label)}"><thead><tr>${heads.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows||`<tr class="no-results"><td colspan="${heads.length}" class="empty">Nenhum registro neste recorte. Tente outra busca.</td></tr>`}</tbody></table></div>`;
const record=(name,sub,symbol='box',action='')=>`<div class="record-name"><span class="product-icon">${icon(symbol)}</span><button class="record-link" data-action="${action}"><strong>${esc(name)}</strong><small>${esc(sub)}</small></button></div>`;
const matching=(text)=>text.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/\p{Diacritic}/gu,'').includes(state.search.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/\p{Diacritic}/gu,''));

function catalogContent(channel=false){
  const list=products.filter(p=>matching(p.name+' '+p.id+' '+p.collection)&&(state.filter==='all'||(state.filter==='available'&&p.status==='À venda')||(state.filter==='out'&&p.stock===0)));
  const rows=list.map(p=>`<tr><td>${record(p.name,p.id,p.icon,'product:'+p.id)}</td>${channel?`<td>${tag(p.status==='Pausado'?'Pausado':'Ativo',p.status==='Pausado'?'':'green')}</td><td>${tag(p.stock===0?'Esgotado':p.status==='Pausado'?'Pausado':'Ativo',p.stock===0?'amber':p.status==='Pausado'?'':'green')}</td><td>${tag(p.id==='CAF'?'Não publicado':p.status==='Pausado'?'Pausado':'Ativo',p.id==='CAF'||p.status==='Pausado'?'':'green')}</td>`:`<td>${esc(p.collection)}</td><td class="numeric">${money(p.price)}</td><td class="numeric">${p.stock===null?'Na hora':number(p.stock)+' un.'}</td><td>${tag(p.status,p.tone,true)}</td>`}<td class="numeric"><button class="icon-button" data-action="product:${p.id}" aria-label="Abrir ${p.name}">${icon('arrow')}</button></td></tr>`).join('');
  return `${toolbar('Buscar produto ou SKU',filterButton('Todos','all')+filterButton('À venda','available')+filterButton('Esgotados','out'))}<p class="count-note">${list.length} ${list.length===1?'produto':'produtos'} neste recorte</p><div class="panel">${table(channel?['Produto','PDV','Loja online','iFood','']:['Produto','Coleção','Preço','Disponível','Situação',''],rows,channel?'Disponibilidade por canal':'Produtos do catálogo')}<div class="panel-footer"><span>Exibindo ${list.length} de ${products.length} produtos da demonstração</span><button class="text-link" data-action="map">Entender a organização</button></div></div>${channel?'<p class="subtle">Canal ativo e produto disponível são condições distintas. Um produto esgotado pode continuar publicado.</p>':''}`;
}
function orderCard(o){return `<article class="order-card ${o.ref==='N099'?'urgent':''}" data-order="${o.ref}"><div class="order-top"><strong>${o.ref}</strong>${tag(o.channel,o.channel==='iFood'?'blue':'')}<time>${o.time}</time></div><h3>${o.name}</h3><p>${o.items}</p><div class="order-foot"><span>${o.delivery}</span><strong>${money(o.total)}</strong></div>${button(o.stage===2?'Ver retirada ou despacho':'Abrir pedido','order:'+o.ref,o.stage===2?'truck':'arrow',o.stage===2?'gold small':'small')}</article>`;}
function queueContent(exit=false){
  const list=orders.filter(o=>matching(o.ref+' '+o.name+' '+o.items)&&(state.filter==='all'||o.delivery.toLowerCase().includes(state.filter)));
  const tools=toolbar('Buscar pedido, cliente ou item',filterButton('Todos','all')+filterButton('Retirada','retirada')+filterButton('Entrega','entrega'));
  if(exit)return `${tools}<div class="banner">${icon('clock')}<div><strong>Uma retirada espera há 24 minutos</strong><p>Confira o pedido N099 antes das próximas saídas.</p></div></div><div class="card-grid">${list.filter(o=>o.stage===2).map(orderCard).join('')||'<div class="empty">Nenhum pedido pronto neste recorte.</div>'}</div>`;
  return `${tools}<div class="board">${['Entrada','Em preparo','Prontos para sair'].map((label,i)=>`<section aria-label="${label}"><div class="column-heading"><span class="stage-dot ${i===1?'blue':i===2?'green':''}"></span>${label}${tag(String(list.filter(o=>o.stage===i).length))}</div>${list.filter(o=>o.stage===i).map(orderCard).join('')||'<div class="empty">Nenhum pedido nesta etapa.</div>'}</section>`).join('')}</div>`;
}
function customerContent(){
  const rows=customers.filter(c=>matching(c.name+' '+c.phone)).map((c,i)=>`<tr><td>${record(c.name,c.phone,'users','customer:'+i)}</td><td>${tag(c.group)}</td><td class="numeric">${c.orders} pedidos</td><td>Hoje</td><td>${button('Abrir','customer:'+i,'arrow','small')}</td></tr>`).join('');
  return `${toolbar('Buscar nome ou telefone')}<div class="panel">${table(['Cliente','Grupo','Histórico','Última compra',''],rows,'Cadastro de clientes')}</div>`;
}
function overviewContent(){
  return `<div class="kpis">${kpi('Precisam de reposição','2','Farinha e manteiga','cart',true)}${kpi('Em conferência','1','Uma nota com diferença de quantidade','file')}${kpi('Insumos cadastrados','6','Cadastro e saldo de estoque','box')}</div><div class="split"><section class="panel"><div class="panel-head"><div><h2>Precisa de atenção</h2><p>Comece pelo que pode interromper o trabalho.</p></div>${tag('3 tarefas','amber')}</div><div class="list-row"><span class="list-icon">${icon('warning')}</span><div><strong>Farinha para menos de um dia</strong><small>18 kg em estoque · Sugestão: 4 sacos de 25 kg</small></div><button class="text-link end" data-view="replenishment">Ver reposição ${icon('arrow')}</button></div><div class="list-row"><span class="list-icon">${icon('file')}</span><div><strong>Faltam 2 kg de manteiga na entrega</strong><small>Nota 004821 · Distribuidora Aurora · Conferência aberta</small></div><button class="text-link end" data-view="divergences">Resolver ${icon('arrow')}</button></div><div class="list-row"><span class="list-icon">${icon('cart')}</span><div><strong>Manteiga para 1,2 dia</strong><small>9 kg em estoque · Sugestão: 10 kg</small></div><button class="text-link end" data-view="replenishment">Ver reposição ${icon('arrow')}</button></div></section><aside class="panel summary-box"><h2>Seu trabalho, por assunto</h2><p class="subtle">Compras reúne reposição, fornecedores e custos. Recebimentos cuida da entrada física. Estoque reúne os insumos e a contagem.</p>${button('Ver organização','map','grid')}</aside></div>`;
}
function replenishmentContent(){
  const list=materials.filter(m=>m.suggestion!=='Não precisa repor'&&matching(m.name+' '+m.supplier)&&(state.filter!=='urgent'||m.urgent));
  const rows=list.map(m=>`<tr><td>${record(m.name,m.id,'box','material:'+m.id)}</td><td class="numeric">${m.stock} ${m.unit}</td><td>${tag(m.coverage,m.urgent?'amber':'')}</td><td><strong>${m.suggestion}</strong><small>${m.supplier}</small></td><td>${button('Revisar','replenish:'+m.id,'arrow','small')}</td></tr>`).join('');
  return `<div class="banner">${icon('warning')}<div><strong>Farinha e manteiga precisam de reposição primeiro</strong><p>A sugestão considera consumo, prazo de entrega e margem de segurança.</p></div></div>${toolbar('Buscar insumo ou fornecedor',filterButton('Todas as sugestões','all')+filterButton('Urgentes','urgent'))}<div class="panel">${table(['Insumo','Em estoque','Cobertura estimada','Sugestão de compra',''],rows,'Sugestões de reposição')}</div><p class="subtle">Comprar não altera o estoque. A entrada acontece na confirmação do recebimento.</p>`;
}
function receiptContent(divergences=false){
  const pending=receipt.filter(r=>!r.resolved).length;
  const list=receipt.filter(r=>(!divergences||r.expected!==r.received)&&matching(r.name+' '+r.sku));
  const rows=list.map(r=>`<tr><td>${record(r.name,r.sku,'box','receipt-item:'+r.id)}</td><td>${r.unit}</td><td class="numeric">${r.expected}</td><td class="numeric">${r.received}</td><td>${tag(r.expected===r.received?'Conferido':r.resolved?'Diferença resolvida':`Faltam ${r.expected-r.received} ${r.unit}`,r.expected===r.received?'green':r.resolved?'blue':'amber')}</td><td>${button(r.resolved?'Ver item':'Resolver diferença','receipt-item:'+r.id,'arrow','small')}</td></tr>`).join('');
  const total=receipt.reduce((s,r)=>s+r.received*r.cost,0);
  return `<div class="receipt-summary"><span class="list-icon">${icon('file')}</span><div><h2>Nota 004821</h2><p>Distribuidora Aurora · Recebida hoje, às 13h40</p></div><div class="end">${tag(pending?'Conferência em aberto':'Conferência concluída',pending?'amber':'green',true)}</div></div>${pending?`<div class="banner">${icon('warning')}<div><strong>Uma diferença precisa de decisão</strong><p>A nota informa 10 kg de manteiga. Foram encontrados 8 kg na entrega.</p></div>${button('Resolver diferença','receipt-item:manteiga','arrow','warning small')}</div>`:''}<div class="split"><div><div class="toolbar">${search('Buscar item nesta nota')}${divergences?button('Ver todos os itens','receiving-all','file','small'):button('Ver divergências','receiving-divergences','warning','small')}</div><div class="panel">${table(['Insumo','Unidade de compra','Na nota','Recebido','Conferência',''],rows,divergences?'Divergências da nota':'Itens da nota de recebimento')}</div><p class="subtle">Farinha: cada saco de 25 kg recebido representa 25 kg no estoque.</p></div><aside class="panel summary-box"><h2>Resumo da entrada</h2><div class="fact"><span>Itens na nota</span><strong>3</strong></div><div class="fact"><span>Diferenças pendentes</span><strong>${pending}</strong></div><div class="fact total"><span>Valor recebido</span><strong>${money(total)}</strong></div>${pending?`<button class="button gold" disabled>Resolva a diferença para confirmar</button>`:button('Confirmar entrada','confirm-receipt','check','gold')}<p class="subtle">A entrada é confirmada depois da conferência. A nota permanece disponível para consulta.</p></aside></div>`;
}
function materialsContent(costs=false){
  const list=materials.filter(m=>matching(m.name+' '+m.id+' '+m.supplier));
  const rows=list.map(m=>`<tr><td>${record(m.name,m.id,'box','material:'+m.id)}</td>${costs?`<td>${esc(m.supplier)}</td><td class="numeric">${money(m.cost)} / ${m.unit}</td><td>27 out. 2026</td>`:`<td class="numeric">${m.stock} ${m.unit}</td><td>${tag(m.urgent?'Reposição urgente':'Saldo suficiente',m.urgent?'amber':'green')}</td><td>${esc(m.supplier)}</td>`}<td>${button(costs?'Ver custo':'Abrir','material:'+m.id,'arrow','small')}</td></tr>`).join('');
  return `${toolbar(costs?'Buscar insumo ou fornecedor':'Buscar insumo ou SKU')}<div class="panel">${table(costs?['Insumo','Fornecedor de referência','Custo por unidade de estoque','Vigência','']:['Insumo','Saldo','Situação','Fornecedor de referência',''],rows,costs?'Custos de compra':'Cadastro de insumos')}</div>${costs?'<p class="subtle">Compare sempre a mesma unidade. O custo de um saco e o custo por kg representam grandezas diferentes.</p>':''}`;
}
function suppliersContent(){
  const list=[['Moinho do Vale','Farinha e insumos de panificação','1 insumo',0],['Laticínios da Serra','Manteiga e laticínios','1 insumo',1],['Distribuidora Aurora','Açúcar, chocolate e mercearia','4 insumos',2]].filter(s=>matching(s.join(' ')));
  return `${toolbar('Buscar fornecedor ou insumo')}<div class="panel">${list.map((s,i)=>`<div class="list-row"><span class="list-icon">${icon('truck')}</span><div><strong>${s[0]}</strong><small>${s[1]}</small></div><span class="end">${tag(s[2])}</span>${button('Abrir','supplier:'+s[3],'arrow','small')}</div>`).join('')||'<div class="empty">Nenhum fornecedor encontrado.</div>'}</div>`;
}
function countContent(){
  const rows=materials.map(m=>`<tr><td>${record(m.name,m.id,'box','material:'+m.id)}</td><td>${m.unit}</td><td><label><span class="sr-only">Quantidade encontrada de ${m.name}</span><input class="row-input" type="number" min="0" step="0.01" data-count="${m.id}" aria-label="Quantidade encontrada de ${m.name}" value="${state.counted[m.id]??''}" placeholder="Contar"></label></td><td>${tag(state.counted[m.id]!==undefined?'Registrado':'A contar',state.counted[m.id]!==undefined?'green':'')}</td></tr>`).join('');
  return `<div class="banner">${icon('check')}<div><strong>Conte o que você encontrou</strong><p>O saldo esperado fica oculto durante a contagem. As diferenças aparecem na revisão.</p></div></div><div class="panel">${table(['Insumo','Unidade de estoque','Quantidade encontrada','Contagem'],rows,'Contagem física de estoque')}</div>`;
}
function genericContent(){
  switch(state.view){
    case 'collections':return `<div class="card-grid">${[...new Set(products.map(p=>p.collection))].map(name=>`<article class="subject-card"><span class="list-icon">${icon('bread')}</span><h2>${name}</h2><p>${products.filter(p=>p.collection===name).length} produtos nesta coleção</p>${button('Ver produtos','collection:'+name,'arrow','small')}</article>`).join('')}</div>`;
    case 'groups':return `<div class="card-grid">${[['Varejo','Condições padrão para o cliente final.','2 clientes'],['Atacado','Condições comerciais para compras recorrentes.','1 cliente'],['Equipe','Condições para pessoas da casa.','Nenhum cliente nesta amostra']].map(g=>`<article class="subject-card"><span class="list-icon">${icon('users')}</span><h2>${g[0]}</h2><p>${g[1]}</p>${tag(g[2])}${button('Ver grupo','group:'+g[0],'arrow','small')}</article>`).join('')}</div>`;
    case 'merges':return `<div class="banner">${icon('users')}<div><strong>Um possível cadastro duplicado</strong><p>Revise os dados antes de decidir. Cadastros parecidos não são necessariamente a mesma pessoa.</p></div></div><div class="panel"><div class="panel-head"><div><h2>Ana Lima e Ana L.</h2><p>Mesmo telefone no cadastro desta demonstração</p></div>${tag('Precisa de revisão','amber')}</div><div class="list-row"><div><strong>Ana Lima</strong><small>12 pedidos · Varejo</small></div><div class="end"><strong>Ana L.</strong><small>2 pedidos · Varejo</small></div></div><div class="panel-footer"><span>Históricos permanecem separados até a decisão.</span>${button('Revisar cadastros','merge','users','gold small')}</div></div>`;
    case 'channels':return `<div class="card-grid">${[['PDV','Balcão e salão','Recebendo pedidos','green'],['Loja online','Retirada e entrega','Recebendo pedidos','green'],['iFood','Pedidos do marketplace','Recebendo pedidos','green'],['WhatsApp','Atendimento conversacional','Em pausa','amber']].map((c,i)=>`<article class="subject-card"><span class="list-icon">${icon('channels')}</span><h2>${c[0]}</h2><p>${c[1]}</p>${tag(c[2],c[3],true)}${button('Ver canal','channel:'+i,'arrow','small')}</article>`).join('')}</div>`;
    case 'routines':return `<div class="panel"><div class="panel-head"><div><h2>Rotinas de hoje</h2><p>Quinta-feira, 29 de outubro · Gestão da loja</p></div>${tag(`${state.done.size} de 4 feitas`,state.done.size===4?'green':'')}</div>${[['Conferir os pedidos agendados','Balcão · antes das 14h'],['Conferir disponibilidade nos canais','Gestão · às 14h'],['Verificar a área de retirada','Expedição · durante o turno'],['Preparar o encerramento do dia','Gestão · antes das 18h']].map((t,i)=>`<div class="task-card"><input type="checkbox" id="task-${i}" data-task="${i}" ${state.done.has(i)?'checked':''}><label for="task-${i}">${t[0]}<small>${t[1]}</small></label>${tag(i===0?'Prioridade':'Rotina',i===0?'amber':'')}</div>`).join('')}</div>`;
    case 'stations':return `<div class="card-grid">${[['Balcão','PDV · Caixa e atendimento','2 dispositivos'],['Expedição','Gestor · Saída dos pedidos','1 dispositivo'],['Cafés','Cozinha · Estação de preparo','1 dispositivo'],['Recebimento','Compras · Conferência de entrada','1 dispositivo']].map(s=>`<article class="subject-card"><span class="list-icon">${icon('grid')}</span><h2>${s[0]}</h2><p>${s[1]}</p>${tag(s[2])}${button('Ver posto','station:'+s[0],'arrow','small')}</article>`).join('')}</div>`;
    case 'history':return `${toolbar('Buscar pedido ou cliente')}<div class="panel">${table(['Pedido','Cliente','Conclusão','Valor',''],[['N096','Ana Lima','Retirado às 13h10',3200],['N097','Rafael Costa','Entregue às 13h25',6800],['N098','Café da Praça','Retirado às 13h40',21600]].filter(o=>matching(o[0]+' '+o[1])).map(o=>`<tr><td><strong>${o[0]}</strong><small>29 out. 2026</small></td><td>${o[1]}</td><td>${tag(o[2],'green')}</td><td>${money(o[3])}</td><td>${button('Ver pedido','historical:'+o[0],'arrow','small')}</td></tr>`).join(''),'Histórico de pedidos')}</div>`;
    default:return '';
  }
}
function renderContent(){
  const renderers={queue:()=>queueContent(),exit:()=>queueContent(true),catalog:()=>catalogContent(), 'channel-catalog':()=>catalogContent(true),customers:customerContent,overview:overviewContent,replenishment:replenishmentContent,receiving:()=>receiptContent(),divergences:()=>receiptContent(true),materials:()=>materialsContent(),costs:()=>materialsContent(true),suppliers:suppliersContent,count:countContent};
  $('#content').innerHTML=(renderers[state.view]||genericContent)();
  $$('table',$('#content')).forEach(t=>{const labels=$$('thead th',t).map(h=>h.textContent);$$('tbody tr',t).forEach(r=>$$('td',r).forEach((td,i)=>td.dataset.label=labels[i]||''));});
}
function renderComparison(){
  $('#comparison').innerHTML=`<div class="comparison-head"><div><h1>Mesmos assuntos. Duas formas de encontrar o trabalho.</h1><p>${applications[state.app].label} · Navegação sincronizada · Mesmos dados e destinos · Área adaptada ao dispositivo</p></div><div class="controls"><select id="compare-destination" class="button" aria-label="Tela para comparar">${applications[state.app].groups.map(g=>`<optgroup label="${g.label}">${g.children.map(c=>`<option value="${c[0]}" ${state.view===c[0]?'selected':''}>${c[1]}</option>`).join('')}</optgroup>`).join('')}</select></div></div><div class="comparison-grid">${['single','double'].map((variant,i)=>`<section class="comparison-card"><div class="comparison-label"><strong><span class="compare-letter">${i?'B':'A'}</span>${i?'Dois níveis':'Lateral única'}</strong><a class="text-link" href="${href({variant,embedded:false,compare:false})}" target="_blank" rel="noopener">Abrir em tamanho real ${icon('arrow')}</a></div><div class="compare-viewport"><iframe title="${i?'B: navegação em dois níveis':'A: lateral única'}" src="${href({variant,embedded:true,compare:false})}"></iframe></div></section>`).join('')}</div><div class="comparison-notes"><strong>Compare a estrutura, mantendo a tarefa.</strong> Na lateral única, os assuntos e seus destinos dividem a mesma coluna. Em dois níveis, a primeira barra escolhe o assunto e a segunda mostra apenas suas opções. Abra uma variante em tamanho real para avaliar leitura, espaço e recolhimento.</div>`;
  const observer=new ResizeObserver(entries=>{for(const entry of entries){const mobile=matchMedia('(max-width:650px), (max-width:900px) and (orientation:portrait)').matches;const scale=mobile?1:entry.contentRect.width/1280;const frame=$('iframe',entry.target);frame.style.width=mobile?'100%':'1280px';frame.style.transform=`scale(${scale})`;entry.target.style.height=mobile?'720px':`${840*scale}px`;frame.style.height=mobile?'720px':'840px';}});
  $$('.compare-viewport').forEach(el=>observer.observe(el));
}
function render(){
  document.body.classList.toggle('embedded',state.embedded);
  document.title=`${applications[state.app].label} · ${viewInfo[state.view][0]} · ${state.compare?'Comparação':state.variant==='single'?'Lateral única':'Dois níveis'} · Prévia Shopman`;
  renderLab();$('#comparison').hidden=!state.compare;$('#app').hidden=state.compare;
  $('#central').hidden=!state.central;$('#quicknav').hidden=state.compare||state.central;
  if(state.central){$('#app').hidden=true;$('#comparison').hidden=true;renderCentral();return;}
  if(state.compare){renderComparison();return;}
  renderNavigation();renderHead();renderContent();renderQuick();
}
function openDialog(title,body,footer=''){
  previousFocus=document.activeElement;
  $('#dialog-content').innerHTML=`<div class="dialog-head"><div><span class="section-label">${applications[state.app].label}</span><h2 id="detail-title">${title}</h2></div><button class="icon-button" data-action="close" aria-label="Fechar detalhe">${icon('close')}</button></div><div class="dialog-body">${body}</div><div class="dialog-foot">${footer||button('Fechar','close')}</div>`;
  $$('table',$('#dialog-content')).forEach(t=>{const labels=$$('thead th',t).map(h=>h.textContent);$$('tbody tr',t).forEach(r=>$$('td',r).forEach((td,i)=>td.dataset.label=labels[i]||''));});
  $('#detail').showModal();
}
const previewNote='<p class="preview-warning">Simulação local com dados fictícios. Nenhuma alteração é enviada ao Shopman.</p>';
function showMap(){
  openDialog('Organização por assuntos',`<div class="map-header"><p>As duas variantes usam os mesmos destinos. Muda a forma de apresentar a hierarquia.</p></div><div class="map-columns">${applications[state.app].groups.map(g=>`<section class="map-column"><h3>${g.label}</h3><ul>${g.children.map(c=>`<li>${c[1]}</li>`).join('')}</ul></section>`).join('')}</div>${previewNote}`);
}
function formDialog(title,fields,action){
  openDialog(title,fields.map(f=>`<label class="field">${f[0]}<input name="${f[1]}" ${f[2]||''}></label>`).join('')+previewNote,button('Cancelar','close')+button('Salvar na prévia',action,'check','gold'));
}
function act(action){
  const [name,...parts]=action.split(':');const id=parts.join(':');
  switch(name){
    case 'compact':if(state.drawer){state.drawer=false;}else{state.hidden=false;state.compact=!state.compact;}renderNavigation();renderHead();break;
    case 'hide':state.hidden=!state.hidden;renderNavigation();renderHead();break;
    case 'secondary':state.secondary=!state.secondary;renderNavigation();renderHead();break;
    case 'drawer':state.drawer=!state.drawer;state.drawerGroup=null;renderNavigation();if(state.drawer)$('a,button',$('#primary'))?.focus();break;
    case 'compare':state.compare=!state.compare;state.embedded=false;history.replaceState(null,'',href());render();break;
    case 'context-mobile':state.drawer=true;state.drawerGroup=currentGroup().id;renderNavigation();$('a,button',$('#primary'))?.focus();break;
    case 'drawer-back':state.drawerGroup=null;renderNavigation();break;
    case 'central':if($('#detail').open)$('#detail').close();state.central=true;state.compare=false;history.pushState(null,'',href());render();break;
    case 'resume':state.central=false;history.pushState(null,'',href());render();break;
    case 'return-context':{const t=state.trail;state.trail=null;state.app=t.app;route(t.view);state.search=t.search;renderContent();if(t.dialog)act(t.dialog);break;}
    case 'cross-product':crossApp('compras','materials','GEL','Produtos · Geleia de frutas vermelhas','product:GEL');break;
    case 'cross-material':crossApp('gestor','catalog','GEL','Insumos · Geleia de frutas vermelhas','material:GEL');break;
    case 'map':showMap();break;
    case 'close':$('#detail').close();break;
    case 'apps':openDialog('Central e apps',`<p>Abra outro app ou volte à Central. O último destino de cada app fica preservado nesta sessão.</p><div class="stack">${button('Central de apps','central','grid')}${button('Gestor · '+viewInfo[state.lastViews.gestor][0],'switch:gestor','orders')}${button('Compras · '+viewInfo[state.lastViews.compras][0],'switch:compras','cart')}</div>${previewNote}`);break;
    case 'switch':$('#detail').close();changeApp(id);break;
    case 'alerts':openDialog('O que pede atenção',`<div class="stack"><button class="button" data-action="jump:gestor:exit">Retirada N099 esperando há 24 minutos ${icon('arrow')}</button><button class="button" data-action="jump:compras:divergences">Diferença no recebimento da nota 004821 ${icon('arrow')}</button><button class="button" data-action="jump:compras:replenishment">Farinha para menos de um dia ${icon('arrow')}</button></div>${previewNote}`);break;
    case 'jump':if($('#detail').open)$('#detail').close();state.lastViews[state.app]=state.view;state.app=parts[0];route(parts[1]);break;
    case 'search-suite':openDialog('Ir direto ao assunto',`<label class="field">Buscar destino<input id="suite-search" placeholder="Ex.: catálogo, contagem, fornecedor" autofocus></label><div id="suite-results" class="stack">${applications[state.app].groups.flatMap(g=>g.children.map(c=>button(`${g.label} · ${c[1]}`,'jump:'+state.app+':'+c[0],'arrow'))).join('')}</div>`);break;
    case 'product':{const p=products.find(x=>x.id===id);formDialog(p.name,[['Nome do produto','product-name',`value="${esc(p.name)}"`],['Preço em reais','price',`type="number" step="0.01" min="0.01" value="${p.price/100}"`]],'save-product:'+p.id);if(p.id==='GEL')$('.dialog-body').insertAdjacentHTML('beforeend',button('Abrir insumo em Compras','cross-product','link'));break;}
    case 'save-product':{const p=products.find(x=>x.id===id);const value=Number($('[name=price]').value);const newName=$('[name=product-name]').value.trim();if(!Number.isFinite(value)||value<=0||!newName){toast('Informe um nome e um preço maior que zero.');break;}p.name=newName;p.price=Math.round(value*100);$('#detail').close();renderContent();toast('Produto atualizado somente nesta prévia.');break;}
    case 'catalog-grid':openDialog('Tabelão do catálogo',`<p>O mesmo cadastro pode ser editado em lote. A navegação proposta mantém esse acesso dentro de Produtos.</p>${table(['Produto','Preço'],products.map(p=>`<tr><td>${p.name}</td><td>${money(p.price)}</td></tr>`).join(''),'Amostra do tabelão')}${previewNote}`);break;
    case 'new-product':formDialog('Novo produto',[['Nome','name','placeholder="Ex.: Pão de campanha"'],['Preço em reais','price','type="number" min="0.01" step="0.01"']],'simulate-save');break;
    case 'new-collection':formDialog('Nova coleção',[['Nome da coleção','name','placeholder="Ex.: Pães do dia"']],'simulate-save');break;
    case 'new-customer':formDialog('Novo cliente',[['Nome','name',''],['Telefone','phone','inputmode="tel"']],'simulate-save');break;
    case 'new-supplier':formDialog('Novo fornecedor',[['Nome','name',''],['Contato','phone','inputmode="tel"']],'simulate-save');break;
    case 'new-material':formDialog('Novo insumo',[['Nome','name',''],['SKU','sku',''],['Unidade de estoque','unit','placeholder="Ex.: kg"']],'simulate-save');break;
    case 'simulate-save':if(!$('[name=name]')?.value.trim()){toast('Preencha o nome antes de continuar.');break;}$('#detail').close();toast('Simulação concluída. O cadastro de demonstração permanece igual.');break;
    case 'collection':route('catalog');state.search=id;renderContent();break;
    case 'order':{const o=orders.find(x=>x.ref===id);openDialog('Pedido '+o.ref,`<div class="fact"><span>Cliente</span><strong>${o.name}</strong></div><div class="fact"><span>Recebimento</span><strong>${o.delivery}</strong></div><div class="fact"><span>Canal</span><strong>${o.channel}</strong></div><p>${o.items}</p><div class="fact total"><span>Total</span><strong>${money(o.total)}</strong></div>${tag(o.stage===2?'Pronto para sair':o.stage===1?'Em preparo':'Na entrada',o.stage===2?'green':'amber')}${previewNote}`,button('Voltar à lista','close')+(o.stage===2?button('Simular entrega','deliver:'+id,'check','gold'):''));break;}
    case 'deliver':$('#detail').close();toast('Entrega simulada. O pedido continua na amostra para comparar as variantes.');break;
    case 'historical':openDialog('Pedido '+id,`<p>Pedido concluído. O histórico e o detalhe ficam em Pedidos, junto da operação.</p><div class="fact"><span>Pagamento</span><strong>Confirmado</strong></div><div class="fact"><span>Atendimento</span><strong>Concluído</strong></div>${previewNote}`);break;
    case 'customer':{const c=customers[Number(id)];openDialog(c.name,`<div class="fact"><span>Telefone</span><strong>${c.phone}</strong></div><div class="fact"><span>Grupo</span><strong>${c.group}</strong></div><div class="fact"><span>Histórico</span><strong>${c.orders} pedidos</strong></div><p>O cadastro e o histórico ficam juntos. A partir daqui, a pessoa pode entender a relação antes de alterar seus dados.</p>${previewNote}`);break;}
    case 'group':openDialog('Grupo '+esc(id),`<p>Condições comerciais e clientes pertencentes ao grupo. A entrada fica junto de Clientes.</p>${previewNote}`);break;
    case 'merge':openDialog('Revisar unificação',`<p>Confirme se Ana Lima e Ana L. são a mesma pessoa. Uma navegação mais curta não elimina essa decisão.</p><div class="fact"><span>Ana Lima</span><strong>12 pedidos</strong></div><div class="fact"><span>Ana L.</span><strong>2 pedidos</strong></div>${previewNote}`,button('Manter separados','close')+button('Simular unificação','simulate-merge','users','gold'));break;
    case 'simulate-merge':$('#detail').close();toast('Unificação simulada. Nenhum cadastro foi alterado.');break;
    case 'channel':openDialog(['PDV','Loja online','iFood','WhatsApp'][Number(id)],`<p>A operação do canal e seu catálogo ficam no mesmo assunto, com destinos próprios.</p>${button('Ver catálogo por canal','go-channel-catalog','grid')}${previewNote}`);break;
    case 'go-channel-catalog':$('#detail').close();route('channel-catalog');break;
    case 'station':openDialog('Posto '+esc(id),`<p>Dispositivos vinculados e trabalho previsto neste posto. Posto, dispositivo e operador permanecem conceitos distintos.</p>${previewNote}`);break;
    case 'material':{const m=materials.find(x=>x.id===id);openDialog(m.name,`<div class="fact"><span>SKU</span><strong>${m.id}</strong></div><div class="fact"><span>Unidade de estoque</span><strong>${m.unit}</strong></div><div class="fact"><span>Saldo</span><strong>${m.stock} ${m.unit}</strong></div><div class="fact"><span>Custo de referência</span><strong>${money(m.cost)} / ${m.unit}</strong></div><div class="fact"><span>Fornecedor</span><strong>${m.supplier}</strong></div>${m.id==='GEL'?button('Abrir produto no Gestor','cross-material','link'):button('Ver sugestão de reposição','go-replenishment','cart')}${previewNote}`);break;}
    case 'go-replenishment':$('#detail').close();route('replenishment');break;
    case 'replenish':{const m=materials.find(x=>x.id===id);openDialog('Repor '+m.name.toLowerCase(),`<div class="fact"><span>Disponível</span><strong>${m.stock} ${m.unit}</strong></div><div class="fact"><span>Cobertura estimada</span><strong>${m.coverage}</strong></div><div class="fact"><span>Sugestão</span><strong>${m.suggestion}</strong></div><div class="fact"><span>Fornecedor</span><strong>${m.supplier}</strong></div><p>A sugestão de compra pertence a Compras. O saldo só muda quando o recebimento é confirmado.</p>${previewNote}`,button('Voltar às sugestões','close')+button('Ver fornecedores','go-suppliers','truck'));break;}
    case 'go-suppliers':$('#detail').close();route('suppliers');break;
    case 'supplier':openDialog(['Moinho do Vale','Laticínios da Serra','Distribuidora Aurora'][Number(id)],`<p>Contato e materiais oferecidos pelo fornecedor, com comparação de custo na unidade correta.</p><div class="fact"><span>Contato fictício</span><strong>(43) 90000-0200</strong></div>${previewNote}`,button('Fechar','close')+button('Ver custos de compra','go-costs','coins'));break;
    case 'go-costs':$('#detail').close();route('costs');break;
    case 'criteria':openDialog('Por que repor agora?',`<p>As sugestões consideram consumo previsto, saldo disponível, prazo de entrega e margem de segurança.</p><p>A prévia mostra esses motivos sem criar novas regras de compra.</p>${previewNote}`);break;
    case 'receiving-all':route('receiving');break;
    case 'receiving-divergences':route('divergences');break;
    case 'receipt-item':{const r=receipt.find(x=>x.id===id);openDialog(r.name,`<div class="fact"><span>Na nota</span><strong>${r.expected} ${r.unit}</strong></div><div class="fact"><span>Recebido</span><strong>${r.received} ${r.unit}</strong></div>${r.expected!==r.received?`<div class="banner">${icon('warning')}<div><strong>Faltam ${r.expected-r.received} ${r.unit}</strong><p>Confirme o que aconteceu antes de continuar.</p></div></div><label class="field">Decisão da conferência<select id="receipt-decision" class="button"><option value="partial">Receber ${r.received} ${r.unit} e registrar a falta</option><option value="correct">Corrigir a contagem para ${r.expected} ${r.unit}</option></select></label>`:'<p>A quantidade recebida corresponde à nota.</p>'}${previewNote}`,button('Voltar à conferência','close')+(r.expected!==r.received?button('Aplicar decisão na prévia','resolve:'+r.id,'check','gold'):''));break;}
    case 'resolve':{const r=receipt.find(x=>x.id===id);if($('#receipt-decision').value==='correct')r.received=r.expected;r.resolved=true;$('#detail').close();renderContent();toast('Diferença resolvida somente nesta prévia.');break;}
    case 'confirm-receipt':openDialog('Confirmar a entrada?',`<p>Os itens conferidos dariam entrada no estoque. Esta ação está apenas representada na prévia.</p>${previewNote}`,button('Voltar','close')+button('Simular confirmação','simulate-receipt','check','gold'));break;
    case 'simulate-receipt':$('#detail').close();toast('Entrada simulada. Nenhum estoque ou recebimento real foi alterado.');break;
    case 'scan':openDialog('Ler uma nota',`<p>O leitor ou a câmera identifica a nota no fluxo real. Aqui você pode continuar a nota fictícia já aberta.</p>${previewNote}`,button('Voltar à nota 004821','close'));break;
    case 'finish-count':{const counted=Object.keys(state.counted).length;openDialog('Revisar contagem',`<p>${counted} de ${materials.length} insumos têm quantidade encontrada registrada.</p>${counted?table(['Insumo','Encontrado'],materials.filter(m=>state.counted[m.id]!==undefined).map(m=>`<tr><td>${m.name}</td><td>${state.counted[m.id]} ${m.unit}</td></tr>`).join(''),'Revisão da contagem'):'<p>Registre as quantidades antes de concluir.</p>'}${previewNote}`,button('Voltar à contagem','close'));break;}
    default:toast('Esta etapa está representada para a comparação de navegação.');
  }
}
function changeApp(app){state.lastViews[state.app]=state.view;state.central=false;state.trail=null;state.app=app;state.view=state.lastViews[app];state.search='';state.filter='all';state.closed=new Set(applications[state.app].groups.filter(g=>!g.children.some(c=>c[0]===state.view)).map(g=>g.id));state.drawer=false;history.pushState(null,'',href());render();}
document.addEventListener('click',event=>{
  const el=event.target.closest('[data-view],[data-action],[data-app],[data-variant],[data-group-toggle],[data-filter],[data-drawer-group],[data-quick-group]');if(!el)return;
  if(el.matches('a')&&(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey))return;
  event.preventDefault();
  if(el.dataset.drawerGroup){const g=applications[state.app].groups.find(g=>g.id===el.dataset.drawerGroup);if(g.children.length===1)route(g.children[0][0]);else{state.drawerGroup=g.id;renderNavigation();$('.drawer-back')?.focus();}return;}
  if(el.dataset.quickGroup){const g=applications[state.app].groups.find(g=>g.id===el.dataset.quickGroup);if(state.variant==='double'&&g.children.length>1){state.drawer=true;state.drawerGroup=g.id;renderNavigation();$('.drawer-back')?.focus();}else route(g.children[0][0]);return;}
  if(el.dataset.app){changeApp(el.dataset.app);return;}
  if(el.dataset.variant){state.variant=el.dataset.variant;state.compare=false;state.drawer=false;history.replaceState(null,'',href());render();return;}
  if(el.dataset.groupToggle){const key=el.dataset.groupToggle;if(state.compact&&!state.drawer){const g=applications[state.app].groups.find(g=>g.id===key);state.compact=false;state.closed.delete(key);route(g.children[0][0]);}else{state.closed.has(key)?state.closed.delete(key):state.closed.add(key);renderNavigation();}return;}
  if(el.dataset.filter){state.filter=el.dataset.filter;renderContent();return;}
  if(el.dataset.view){route(el.dataset.view);return;}
  if(el.dataset.action)act(el.dataset.action);
});
$('#scrim').addEventListener('click',()=>{state.drawer=false;renderNavigation();$('.mobile-menu')?.focus();});
document.addEventListener('input',event=>{
  if(event.target.matches('[data-search-input]')){const pos=event.target.selectionStart;state.search=event.target.value;renderContent();const input=$('[data-search-input]');input.focus();input.setSelectionRange(pos,pos);}
  if(event.target.id==='suite-search'){const text=event.target.value.toLowerCase();$$('#suite-results button').forEach(b=>b.hidden=!b.textContent.toLowerCase().includes(text));}
  if(event.target.matches('[data-count]')){const key=event.target.dataset.count;const value=event.target.value;if(value==='')delete state.counted[key];else if(Number(value)>=0)state.counted[key]=Number(value);}
});
document.addEventListener('change',event=>{
  if(event.target.id==='mobile-destinations'||event.target.id==='compare-destination'){route(event.target.value);return;}
  if(event.target.matches('[data-task]')){const id=Number(event.target.dataset.task);event.target.checked?state.done.add(id):state.done.delete(id);renderContent();}
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&state.drawer){event.preventDefault();state.drawer=false;state.drawerGroup=null;renderNavigation();$('.mobile-menu')?.focus();}
  if(state.drawer&&event.key==='Tab'){const nodes=$$('a,button:not([disabled])',$('#primary'));if(event.shiftKey&&document.activeElement===nodes[0]){event.preventDefault();nodes.at(-1).focus();}else if(!event.shiftKey&&document.activeElement===nodes.at(-1)){event.preventDefault();nodes[0].focus();}}
});
$('#detail').addEventListener('close',()=>{if(previousFocus?.isConnected)previousFocus.focus();});
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||!event.data||typeof event.data!=='object')return;
  if(state.compare&&event.data.type==='shopman-preview-route'&&$$('iframe').some(f=>f.contentWindow===event.source)){
    if(event.data.app!==state.app)return;
    const view=event.data.view;if(!applications[state.app].groups.some(g=>g.children.some(c=>c[0]===view)))return;
    state.view=view;history.replaceState(null,'',href());$('#compare-destination').value=view;
    $$('iframe').filter(f=>f.contentWindow!==event.source).forEach(f=>f.contentWindow.postMessage({type:'shopman-preview-set-route',view},location.origin));
  }else if(state.embedded&&event.source===parent&&event.data.type==='shopman-preview-set-route')route(event.data.view,false);
});
let narrowLayout=matchMedia('(min-width:651px) and (max-width:1100px) and (orientation:landscape)').matches;
window.addEventListener('resize',()=>{const next=matchMedia('(min-width:651px) and (max-width:1100px) and (orientation:landscape)').matches;if(next!==narrowLayout){narrowLayout=next;state.compact=next;if(!state.compare&&!state.central){renderNavigation();renderHead();}}});
window.addEventListener('popstate',()=>{const q=new URLSearchParams(location.search);state.app=q.get('app')==='compras'?'compras':'gestor';state.variant=q.get('variant')==='double'?'double':'single';state.view=q.get('view')||applications[state.app].home;state.compare=q.get('compare')==='1';state.central=q.get('screen')==='central';state.trail=null;state.drawer=false;if(!applications[state.app].groups.some(g=>g.children.some(c=>c[0]===state.view)))state.view=applications[state.app].home;render();});
render();
