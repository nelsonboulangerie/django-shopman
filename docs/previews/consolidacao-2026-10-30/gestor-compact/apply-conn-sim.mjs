// Só simulação, aplicada IGUAL em A e C: `?conn=live|calm|late|off` força a ENTRADA do
// indicador de conexão que já existe no quadro (tom), para comparar os estados sem
// derrubar o mock. Não muda o indicador, a leitura nem o tratamento de erro (o erro real
// de leitura é o cenário `error` do mock).
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do orders-nuxt.');
const file=join(root,'app/pages/index.vue');let s=await readFile(file,'utf8');
const tone='const liveTone = computed(() =>\n  error.value\n    ? "off"';
if(!s.includes(tone))throw Error('Revisar o encaixe do indicador de conexão (index.vue).');
s=s.replace(tone,`const previewConnRoute = useRoute();
const previewConn = useState<string>('preview-conn', () => String(previewConnRoute.query.conn || ''));
watch(() => previewConnRoute.query.conn, (v) => { if (typeof v === 'string') previewConn.value = v; });
const liveTone = computed(() =>
  ['live', 'calm', 'late', 'off'].includes(previewConn.value)
    ? (previewConn.value as 'live' | 'calm' | 'late' | 'off')
    : error.value
    ? "off"`);
await writeFile(file,s);
