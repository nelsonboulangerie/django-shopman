// Só simulação, aplicado igualmente em A, B e C: `?conn=live|calm|late|off` força a ENTRADA
// do indicador de conexão que já existe (tom e rótulo), para comparar os estados sem
// derrubar o mock. Não muda o indicador, a leitura nem o tratamento de erro.
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do KDS.');
const file=join(root,'app/pages/[ref].vue');let s=await readFile(file,'utf8');
const tone='const liveTone = computed(() => {\n  if (error.value)';
const label='const liveLabel = computed(() => {\n  if (error.value)';
if(!s.includes(tone)||!s.includes(label))throw Error('Revisar o encaixe do indicador de conexão.');
s=s.replace(tone,`const previewConnRoute = useRoute();
const previewConn = useState<string>('preview-conn', () => String(previewConnRoute.query.conn || ''));
watch(() => previewConnRoute.query.conn, (v) => { if (typeof v === 'string') previewConn.value = v; });
const liveTone = computed(() => {
  if (['live', 'calm', 'late', 'off'].includes(previewConn.value)) return previewConn.value as 'live' | 'calm' | 'late' | 'off';
  if (error.value)`);
s=s.replace(label,`const liveLabel = computed(() => {
  if (previewConn.value === 'off') return 'Sem conexão';
  if (previewConn.value === 'live') return liveCue.value.label;
  if (error.value)`);
s=s.replace('<OperatorScreenState v-else-if="error && view" state="offline" :since="lastRead" />','<OperatorScreenState v-else-if="(error || previewConn === \'off\') && view" state="offline" :since="lastRead" />');
await writeFile(file,s);
