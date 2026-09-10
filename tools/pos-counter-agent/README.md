# Agente do balcão

Processo local, sem dependências, que recebe um pedido do PDV em `127.0.0.1` e
entrega bytes crus à impressora térmica pelo spooler: o kick ESC/POS que abre a
gaveta e o papel que o servidor compôs (comprovante de movimento de caixa hoje,
DANFE NFC-e depois — obrigação legal). Opcionalmente, a mesma instância busca
por HTTPS trabalhos duráveis criados por tablets: o tablet nunca chama a
loopback do PC nem recebe segredo do agente. Ele é a ponte com o hardware; a
gaveta é um dos aparelhos que ele alcança, não o escopo dele.

**Por que ele existe:** a gaveta não tem cabo próprio — ela pendura no RJ11 da
impressora e abre quando a impressora recebe `ESC p m t1 t2`. O PDV roda no
navegador, e navegador não fala ESC/POS. Como a TM-T20 é USB e o driver do
sistema já é dono da interface, WebUSB está fora (brigar pela interface quebraria
a impressão do recibo). Sobra entregar os cinco bytes ao **spooler**, pela mesma
fila por onde o recibo já sai.

Desenho e alternativas descartadas: [POS-CASH-DRAWER-PLAN](../../docs/plans/POS-CASH-DRAWER-PLAN.md).

## Instalar (Linux oficial; Windows e macOS também)

**Comece pelo Admin**, não por aqui: Terminais do PDV → o balcão → *Baixar o
agente e ver como instalar*. Aquela tela entrega o arquivo e o comando **já
preenchido** com o token, a fila e a origem daquele terminal. Nada a transcrever.

É **um arquivo só** — `counter_agent.py`. Leve até o balcão por qualquer meio
(pendrive, `scp`, ou colando num editor) e rode o comando que a tela mostrou:

```bash
python3 counter_agent.py --install --token TOKEN-DO-ADMIN --origin https://pdv.boulangerie.com.br
# no Windows, `python` no lugar de `python3`
```

Ele lista as impressoras e pergunta qual é a da térmica (ela já existe: é por ela
que o recibo imprime hoje). Passe `--queue` para não ser perguntado.

| | envio dos bytes | início automático | registro |
|---|---|---|---|
| **Linux** (oficial) | `lp -o raw` | systemd `--user` + linger | journald |
| **macOS** | `lp -o raw`, idêntico | LaunchAgent | arquivo em `~/.local/share/nelson-pos-counter/` |
| **Windows** | winspool (`ctypes`, datatype `RAW`) | tarefa no logon | arquivo em `%LOCALAPPDATA%\NelsonPosCounter\` |

⚠️ O **Windows não traz Python de fábrica** — instale pela Microsoft Store se o
comando não for reconhecido. Linux e macOS já vêm com ele.

⚠️ O caminho Windows **não foi executado em Windows nenhum** aqui; os testes
travam o despacho e o contrato, o resto o balcão confirma.

**Sem `--token`** ele gera um e imprime na tela para você colar no Admin. É o
caminho de emergência, para quem estiver no balcão sem acesso ao Admin — o
normal é o Admin ser o dono do par.

Reinstalar preserva o token guardado; só um `--token` diferente rotaciona. O PDV
levaria 401 até os dois lados baterem, e ninguém quer descobrir isso no sábado.

Para habilitar também a impressão iniciada por tablets, use o comando completo
emitido pelo Admin. A forma é:

```bash
python3 counter_agent.py --install --token TOKEN-LOCAL --origin https://pdv.example \
  --server-url https://gestor.example --station preparo-01 \
  --relay-token CREDENCIAL-DO-RELAY
```

`--agent-id` é opcional: na primeira instalação nasce um UUID estável. O token
local e a credencial do relay são separados. Nenhum deles é enviado ao tablet.
O instalador nunca imprime a credencial do relay e mantém o arquivo em modo
`600`.

### Numa máquina que já rodava o agente antigo

O instalador **derruba o serviço antigo antes de subir o novo** (`stop`,
`disable` e a unit/tarefa apagada) e **move o `agent.json`** do caminho antigo,
para o token continuar batendo com o do Admin. Não é opcional: enquanto o
serviço antigo estiver de pé, ele segura a porta 47811, o novo não sobe, e o
`/health` responde — com o código velho. Reinstalar não resolveria, porque
reinstalar é exatamente o que não estaria pegando.

O instalador confere isso por conta própria: no fim ele bate no `/health` e
compara o `build` (sha256 do arquivo). Se quem atende não for este arquivo, ele
**reprova** e diz quem está na porta.

## Config

`~/.config/nelson-pos-counter/agent.json`, modo 600:

```json
{
  "queue": "TM-T20",
  "token": "…",
  "port": 47811,
  "host": "127.0.0.1",
  "allowed_origins": ["https://pdv.boulangerie.com.br"],
  "server_url": "https://gestor.example",
  "station_ref": "preparo-01",
  "agent_id": "UUID-estavel",
  "relay_token": "…",
  "relay_poll_seconds": 2
}
```

Só fatos **da máquina**. O pulso e a política (adapter, abrir-na-venda) moram no
Django, por terminal, e chegam no request — para não existirem dois donos da
mesma resposta.

O relay é opcional: configs antigas, sem esses quatro campos, continuam no modo
local. Se um campo do relay estiver presente, `server_url`, `station_ref`,
`agent_id` e `relay_token` precisam formar um conjunto completo. O servidor deve
ser HTTPS. `host` aceita somente `127.0.0.1`, `::1` ou `localhost`.

## API

| rota | corpo | resposta |
|---|---|---|
| `POST /kick` | `{token, reason, pulse:{pin,on_ms,off_ms}}` | `{ok, queue, job_id}` |
| `POST /print` | `{token, title, payload_b64}` | `{ok, queue, job_id}` |
| `GET /health` | — | `{ok, accepting, queue, reason, version, build}` |

O `/print` recebe bytes **já compostos pelo servidor**. O agente é um cano: não
sabe o que é sangria nem leiaute. Se cada balcão compusesse, dois imprimiriam
diferente — e a DANFE, cujo leiaute a lei define, teria de ser reimplementada em
cada máquina.

`GET /health` pergunta ao CUPS se a fila existe e aceita trabalho. Ele **não**
sabe se a gaveta está plugada nem se abriu: isso viria pelo canal bidirecional
da impressora, que um job de spool não tem. Quem confirma é o olho do operador
no teste de gaveta.

### Relay de impressão

O relay roda em outra thread; conexão lenta ou servidor offline não bloqueiam
`/kick`, `/print` nem `/health`. Ele usa somente stdlib (`urllib` e `sqlite3`):

1. `POST /api/v1/backstage/print-agent/jobs/claim/` com Bearer da credencial;
2. valida `job_ref`, `lease_token`, base64, `payload_sha256` dos bytes RAW e o
   teto de 512 KiB;
3. grava `claimed` e depois `spooling` no SQLite **antes** de chamar o spooler;
4. grava `submitted_to_spooler` e o `spooler_job_id` quando o spooler aceita;
5. envia `POST /api/v1/backstage/print-agent/jobs/<job_ref>/ack/` com
   `status=spooled|failed|uncertain`, `lease_token` e `payload_sha256`.

`content_sha256`, quando vier, é metadado adicional e nunca substitui
`payload_sha256`. `station_ref` e `agent_id` também são metadados: o servidor
deve derivar a identidade autorizada da credencial, não confiar no corpo.

“`spooled`” quer dizer apenas **aceito pela fila**, nunca “papel impresso”. Se o
ACK se perder, a reentrega repete só o ACK. Se o processo cair enquanto chama o
spooler, o resíduo `spooling` vira `uncertain` no próximo início e não imprime
de novo automaticamente. Uma reimpressão intencional deve nascer no servidor
como novo trabalho auditado, com outro `job_ref`.

O journal fica em `~/.local/share/nelson-pos-counter/print-relay.sqlite3`. Ele
guarda referências, hashes, estados, detalhe curto, id do spooler e o lease
temporário necessário para concluir um ACK depois de restart — nunca o payload
nem a credencial permanente do relay. O arquivo também é `600`. Em cada ciclo,
o agente drena primeiro todos os ACKs pendentes e só então pede outro trabalho;
o servidor pode conservar apenas o digest do lease. Rede offline usa backoff
exponencial de 1 a 60 segundos e volta sozinha.

O journal identifica também o número de `attempt`. Se o servidor reutilizar o
mesmo `job_ref` num retry, um lease novo só reabre o fluxo quando a ocorrência
anterior terminou em `failed` **e seu ACK já foi aceito**. `spooled`,
`uncertain` ou qualquer ACK ainda pendente permanecem fechados para não produzir
uma segunda etiqueta. Retry de payload rejeitado segue a mesma regra.

## Segurança

CORS não protege endpoint com efeito colateral — um `POST` simples *chega* aqui
mesmo com a resposta bloqueada pelo navegador. Quem protege é o **token**; a
allowlist de origem é a segunda tranca. Sem token, qualquer aba aberta no balcão
abre a gaveta de dinheiro.

O agente escuta só em loopback. A configuração recusa qualquer outro host; não
há modo LAN. Uma allowlist vazia também **não** libera páginas arbitrárias:
pedidos de navegador com `Origin` são recusados. Chamadas locais sem `Origin`
continuam compatíveis e ainda exigem o token.

## Diagnóstico

```bash
systemctl --user status nelson-pos-counter
```

```bash
journalctl --user -u nelson-pos-counter -f
```

Cada kick vira uma linha (`kick OK motivo=… fila=… job=…`). O journal é a
verdade **física** do balcão; o servidor só sabe o que a tela mandou.

Testar o caminho até o spooler sem navegador:

```bash
python3 ~/.local/share/nelson-pos-counter/counter_agent.py --kick
```

Ver configuração local, estado do serviço, fila e resumo do journal sem expor a
credencial do relay:

```bash
python3 ~/.local/share/nelson-pos-counter/counter_agent.py --doctor
```

## Testes

```bash
python3 -m pytest tools/pos-counter-agent/test_counter_agent.py -v
```
