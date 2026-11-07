import {readFile,writeFile,copyFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
const [source,out]=process.argv.slice(2);if(!source||!out)throw Error('Informe tests/e2e original e diretório de saída.');
await mkdir(out,{recursive:true});
let fixtures=await readFile(join(source,'previewFixtures.mjs'),'utf8');
const marker='export function createPreviewState() {';
if(!fixtures.includes(marker))throw Error('Fixture diferente: revisar a extensão.');
fixtures=fixtures.slice(0,fixtures.indexOf(marker))+await readFile(new URL('preview-state.mjs',import.meta.url),'utf8');
await writeFile(join(out,'previewFixtures.mjs'),fixtures);
let mock=await readFile(join(source,'mockBackend.mjs'),'utf8');
mock=mock.replace('const server = createServer','let previewFailure=null;\nconst server = createServer');
mock=mock.replace('  const url = req.url || "";',`  const url = (req.url || '').replace('/api/v1/backstage/__preview/','/__preview/');
  if(preview && req.method==='POST' && url.startsWith('/__preview/fail-next')) {
    let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{try{previewFailure=JSON.parse(raw);}catch{previewFailure={};}json(res,200,{ok:true});});return;
  }
  if(previewFailure && (!previewFailure.path||url.includes(previewFailure.path)) && (!previewFailure.method||previewFailure.method===req.method)) {
    const f=previewFailure;previewFailure=null;return json(res,f.status||503,{detail:f.detail||'Falha simulada. O quadro será relido e a ação pode ser repetida.',field:'',errors:[]});
  }
  if(preview && req.method==='POST') {
    const volume=url.match(/\\/orders\\/([^/]+)\\/volumes\\//);
    if(volume){let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{let body={};try{body=JSON.parse(raw);}catch{}const r=preview.volumes(decodeURIComponent(volume[1]),body.volumes,body.base_revision);json(res,r.status,r.body);});return;}
    const result=preview.command(url);if(result)return json(res,result.status,result.body);
  }`);
mock=mock.replace('preview.reset();','preview.reset(); previewFailure=null;');
mock=mock.replace('return json(res, 200, {});\n});','return json(res, 501, {detail:"Este cenário ainda não é coberto pelo simulador.",field:"",errors:[]});\n});');
await writeFile(join(out,'mockBackend.mjs'),mock);
