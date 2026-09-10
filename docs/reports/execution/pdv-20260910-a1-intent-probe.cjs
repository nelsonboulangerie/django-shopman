// Diagnóstico de F03/F07: documenta lacunas, não é gate de aceite do produto.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const ts = createRequire(path.resolve('surfaces/pos-nuxt/package.json'))('typescript');
const source = fs.readFileSync('surfaces/pos-nuxt/app/utils/posIntent.ts', 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } });
const context = { exports: {}, require: () => ({ POS_SALE_INTENT_VERSION: 1 }) };
vm.runInNewContext(compiled.outputText, context);
console.log(JSON.stringify({
  probe: 'F03',
  input: { method: 'pix', amount_q: 500, collection: 'terminal', reference: 'synthetic' },
  total_q: 1000,
  result: context.exports.resolvePayment([{ method: 'pix', amount_q: 500, collection: 'terminal', reference: 'synthetic' }], 1000),
}));
console.log(JSON.stringify({
  probe: 'F07', actions: [],
  result: context.exports.actionHref([], 'close_sale', '/api/v1/backstage/pos/sale/close/'),
}));
