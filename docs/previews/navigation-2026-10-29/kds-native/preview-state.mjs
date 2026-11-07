// Substitui somente o estado fictício, dentro da cópia temporária da prévia.
export function createPreviewState() {
  const clone = value => structuredClone(value);
  let active, cancelled, history, settings;
  const failure=(status,detail)=>({status,body:{detail,field:'',errors:[]}});
  function reset() {
    active={bancada:clone(PREP_TICKETS),cafes:clone(CHANGED_TICKETS),lanches:[],encomendas:[{...clone(HISTORY_ENTRIES[1].ticket),pk:401,status:'in_progress',status_label:'Em separação'}]};
    cancelled={bancada:[],cafes:clone(CANCELLED_TICKETS),lanches:[],encomendas:[]};
    history={bancada:clone(HISTORY_ENTRIES),cafes:[],lanches:[],encomendas:[]};settings={};
    for(const [ref,list] of Object.entries(active))for(const t of list){
      // O detalhe usa os mesmos campos de volumes do contrato atual.
      if(t.order_ref.startsWith('WEB-')||ref==='encomendas')Object.assign(t,{volumes_order_ref:t.order_ref,volumes:0,volumes_revision:'preview-1',volumes_actor_id:1});
    }
  }
  function locate(pk) {
    for(const ref of Object.keys(active)) {
      const i=active[ref].findIndex(t=>t.pk===pk);if(i>=0)return {ref,list:active[ref],i,t:active[ref][i]};
      const c=cancelled[ref].findIndex(t=>t.pk===pk);if(c>=0)return {ref,list:cancelled[ref],i:c,t:cancelled[ref][c],cancelled:true};
    }
    return null;
  }
  reset();
  return {
    reset,
    index() { return {instances:PREVIEW_INDEX.instances.map(i=>({...i,active_count:active[i.ref]?.length??i.active_count}))}; },
    saveSettings(ref,change) {const current={density:'cozy',sound_enabled:true,...settings[ref]};if(['compact','cozy','roomy'].includes(change?.density))current.density=change.density;if(typeof change?.sound_enabled==='boolean')current.sound_enabled=change.sound_enabled;settings[ref]=current;return clone(current);},
    board(ref) {const name=PREVIEW_INDEX.instances.find(i=>i.ref===ref)?.name||ref;
      const data=boardFor(ref,active[ref]||[],name,cancelled[ref]||[],settings[ref]);
      data.board.instance_type=ref==='encomendas'?'picking':'prep';
      return data;
    },
    history(ref,query) {const q=String(query||'').trim().toLowerCase();const entries=(history[ref]||[]).filter(e=>!q||e.ticket.order_ref.toLowerCase().includes(q));return {history:{instance_ref:ref,instance_name:PREVIEW_INDEX.instances.find(i=>i.ref===ref)?.name||ref,entries,total:entries.length,query:q}};},
    volumes(orderRef,count,revision) {
      if(!Number.isInteger(count)||count<0||count>99)return failure(422,'Declare um número inteiro de volumes, de 0 a 99.');
      const tickets=[...Object.values(active).flat(),...Object.values(history).flat().map(e=>e.ticket)].filter(t=>t.volumes_order_ref===orderRef);
      if(!tickets.length)return failure(404,'Pedido não encontrado na demonstração.');
      if(revision&&tickets[0].volumes_revision!==revision)return failure(409,'Os volumes mudaram. Atualize antes de tentar novamente.');
      for(const t of tickets){t.volumes=count;t.volumes_revision=`preview-${count}-${Date.now()}`;}
      return {status:200,body:{ok:true}};
    },
    command(url) {
      const stationSeen=url.match(/\/kds\/([^/]+)\/seen\//);
      if(stationSeen){for(const t of active[stationSeen[1]]||[])t.seen=true;return {status:200,body:{ok:true}};}
      const route=url.match(/\/kds\/tickets\/(\d+)\/(start|done|recall|changes\/seen|acknowledge)\//);if(!route)return null;
      const pk=Number(route[1]),act=route[2],found=locate(pk);
      if(act==='recall') {
        for(const [ref,entries] of Object.entries(history)) {
          const i=entries.findIndex(e=>e.ticket.pk===pk);if(i<0)continue;
          if(!entries[i].can_reopen)return failure(409,entries[i].reopen_block_reason||'Este pedido não pode voltar para a cozinha.');
          const entry=entries.splice(i,1)[0];active[ref].unshift({...clone(entry.ticket),status:'in_progress',status_label:'Em preparo',seen:true});
          return {status:200,body:{ok:true}};
        }
        if(found)return {status:200,body:{ok:true}};
        return failure(404,'Pedido não encontrado no histórico.');
      }
      if(!found)return failure(404,'Ticket não encontrado. Restaure a demonstração para recomeçar.');
      const {ref,list,i,t}=found;
      if(act==='start'){if(t.status!=='pending'&&t.status!=='in_progress')return failure(409,'Este ticket não pode ser iniciado.');t.status='in_progress';t.status_label='Em preparo';}
      if(act==='done') {
        if(t.is_cancelled||t.status!=='in_progress'||t.finish_block_label||t.changes?.length)return failure(409,'Confira o estado e as mudanças do ticket antes de marcar Pronto.');
        list.splice(i,1);history[ref].unshift({ticket:{...clone(t),status:'done',status_label:'Concluído'},state:'done',undone:[],steps:['Recebido na estação','Pronto por Admin (demonstração)'],prep_display:'5 min',can_reopen:true,reopen_block_reason:'',items_summary:t.items.map(i=>`${i.qty}× ${i.name}`).join(', ')});
      }
      if(act==='changes/seen'){t.changes=[];t.change_ticket_pks=[];}
      if(act==='acknowledge') {
        if(!found.cancelled)return failure(409,'Este ticket não está cancelado.');
        list.splice(i,1);history[ref].unshift({ticket:clone(t),state:'cancelled',undone:[],steps:['Cancelamento recebido por Admin (demonstração)'],prep_display:'',can_reopen:false,reopen_block_reason:'Pedido cancelado.',items_summary:t.items.map(i=>`${i.qty}× ${i.name}`).join(', ')});
      }
      return {status:200,body:{ok:true}};
    },
    // Mantém a assinatura do mock original; o interceptor usa command para status.
    write(url) {return Boolean(this.command(url));},
  };
}
