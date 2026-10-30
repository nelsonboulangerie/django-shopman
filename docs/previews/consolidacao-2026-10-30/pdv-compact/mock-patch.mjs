// PRÉVIA (A e C iguais). Completa o simulador da prévia anterior (prepare-mock +
// mock-extension de origin/codex/shopman-ux-product-review) com o que esta comparação
// precisa e ele devolvia 501: a caixa de Avisos (dois avisos fictícios) e a consulta de
// cliente da comanda (200 vazio, como o mock visual original). Dados fictícios.
import {readFile,writeFile} from 'node:fs/promises';
const file=process.argv[2];if(!file)throw Error('Informe o mockBackend.mjs gerado.');
let s=await readFile(file,'utf8');
const anchor='  try { if (await previewHandle(req,res,url)) return;';
if(!s.includes(anchor))throw Error('Encaixe ausente no simulador: revisar prepare-mock.');
s=s.replace(anchor,`  if (path === '/api/v1/backstage/notifications/') { send(res, 200, { unread_count: 2, actionable_count: 1, notifications: [
    { pk: 1, category: 'order', title: 'Encomenda NB-1042 mudou de horário', message: 'Agora às 12h (demonstração).', action_url: '/preorders/NB-1042', action_label: 'Abrir encomenda', action_data: {}, is_actionable: true, is_read: false, created_at: '2026-09-29T11:40:00-03:00', created_at_display: '11:40' },
    { pk: 2, category: 'system', title: 'Impressora do Caixa 2 sem papel', message: 'Aviso fictício da prévia.', action_url: '', action_data: {}, is_actionable: false, is_read: false, created_at: '2026-09-29T10:05:00-03:00', created_at_display: '10:05' } ] }); return; }
  if (path === '/api/v1/backstage/pos/customer/lookup/') { send(res, 200, {}); return; }
${anchor}`);
await writeFile(file,s);
