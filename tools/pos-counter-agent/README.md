# Agente do balcão

Processo local, sem dependências, que recebe um pedido do PDV em `127.0.0.1` e
entrega bytes crus à impressora térmica pelo spooler: o kick ESC/POS que abre a
gaveta e o papel que o servidor compôs (comprovante de movimento de caixa hoje,
DANFE NFC-e depois — obrigação legal). Opcionalmente, a mesma instância busca
por HTTPS trabalhos duráveis criados por tablets: o tablet nunca chama a
loopback do PC nem recebe segredo do agente. Ele é a ponte com o hardware; a
gaveta é um dos dispositivos que ele alcança, não o escopo dele.

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
  --relay-token-prompt
```

O instalador pede a credencial em seguida, sem mostrá-la na tela nem gravá-la
no histórico do terminal. Copie o segredo separado que o Admin exibe uma única
vez e cole nesse prompt.

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

`extra_printers` também é opcional e só existe quando o balcão atende mais de
uma impressora — ver [Uma segunda impressora](#uma-segunda-impressora-ex-cozinha).
Sem ela, nada muda.

## API

| rota | corpo | resposta |
|---|---|---|
| `POST /kick` | `{token, reason, pulse:{pin,on_ms,off_ms}}` | `{ok, queue, job_id}` |
| `POST /print` | `{token, title, payload_b64}` | `{ok, queue, job_id}` |
| `GET /health` | — | `{ok, accepting, queue, reason, version, build, …, extra_printers}` |

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

## Uma segunda impressora (ex. cozinha)

O mesmo agente pode atender, além da impressora do balcão, outras impressoras da
mesma rede — por exemplo a Epson TM-T20X que imprime a **Via Cozinha** do posto
Lanches do KDS. Para o servidor, cada uma é um **Terminal** com a sua própria
credencial de relay; o agente só pede trabalho em nome de cada uma e entrega na
fila certa.

**A impressora do balcão não é tocada.** `queue`, `token`, credencial do relay,
gaveta, `/kick`, `/print` e o journal `print-relay.sqlite3` seguem exatamente
como estão. A impressora extra não tem gaveta nem rota local: ela só recebe o
que o servidor manda pelo relay.

Cada impressora extra tem:

- **thread própria**, com backoff próprio de 1 a 60 s: sem papel, desligada,
  credencial revogada ou qualquer erro inesperado ficam nela — a do balcão
  continua imprimindo;
- **journal próprio**, ao lado do principal:
  `print-relay-<ref>.sqlite3` (a mesma garantia de nunca imprimir duas vezes);
- **linha própria no `/health`**, em `extra_printers`.

### 1. Adicionar a impressora de rede no sistema

A impressora entra como **fila do sistema**, igual à do balcão. O agente não
abre conexão direta com a porta 9100.

**Windows** (Configurações → Bluetooth e dispositivos → Impressoras e scanners):

1. *Adicionar dispositivo* → *A impressora que eu quero não está na lista* →
   *Adicionar uma impressora usando um endereço TCP/IP ou nome de host*.
2. Tipo *Dispositivo TCP/IP*, endereço = o IP da TM-T20X (fixe esse IP no
   roteador, senão a fila se perde quando ele mudar). Porta padrão (9100, *Raw*).
3. Driver: *Generic* → *Generic / Text Only*, ou o driver Epson da TM-T20X. O
   agente sempre manda os bytes em modo RAW, então os dois servem.
4. Dê um nome curto e sem acento, ex. `Cozinha Lanches`. **Esse nome é a
   `queue`.**

**Linux / macOS** (CUPS):

```bash
sudo lpadmin -p Cozinha-Lanches -E -v socket://192.168.0.50:9100
lpstat -a Cozinha-Lanches     # deve dizer "accepting requests"
```

Troque o IP pelo da TM-T20X. No macOS sem `sudo` configurado, adicione pelo
painel *Impressoras e Scanners* → *IP* → protocolo *HP Jetdirect – Socket* e use
o nome que aparecer em `lpstat -a`.

### 2. Emitir a credencial do Terminal da impressora no Admin

1. Admin → Terminais do PDV → o terminal dessa impressora (ex.
   `cozinha-lanches`; crie se ainda não existir). Ative a impressora de
   preparação pelo agente local e salve — a página do agente só libera a
   credencial depois disso. Confira também que o posto do KDS manda a Via
   Cozinha para este terminal.
2. Abra *Baixar o agente e ver como instalar* (`/admin/pos/terminal/<ref>/agent/`)
   → *Ativar impressão por tablets* → *Gerar o comando completo*.
3. Copie **só o segredo** (*Copiar segredo*). Ele aparece uma vez.

⚠️ **Não rode o comando `--install` que essa tela mostra no PC do balcão.** Ele é
do terminal da cozinha e trocaria o token e a credencial do relay **do balcão**
pelos da cozinha — o PDV passaria a levar 401 e a gaveta deixaria de abrir.

### 3. Acrescentar o item em `extra_printers`

Edite o `agent.json` do balcão (Linux/macOS: `~/.config/nelson-pos-counter/agent.json`;
Windows: `%LOCALAPPDATA%\NelsonPosCounter\agent.json`) e **acrescente** a chave,
sem mexer no resto:

```json
{
  "queue": "TM-T20",
  "token": "…",
  "server_url": "https://gestor.example",
  "station_ref": "pdv-balcao",
  "agent_id": "UUID-estavel",
  "relay_token": "…",

  "extra_printers": [
    {
      "ref": "cozinha-lanches",
      "queue": "Cozinha Lanches",
      "station_ref": "cozinha-lanches",
      "relay_token": "SEGREDO-COPIADO-DO-ADMIN"
    }
  ]
}
```

Os campos são os mesmos do relay da config principal, dentro de cada item:

| campo | obrigatório | o que é |
|---|---|---|
| `ref` | sim | nome desta impressora no agente (letras, números, `-`, `_`); vira o nome do journal e a linha no `/health`. Único. |
| `queue` | sim | nome da fila no sistema (passo 1). |
| `relay_token` | sim | o segredo do passo 2 (mínimo 16 caracteres). **Nunca** herdado do balcão. |
| `station_ref` | não | ref do Terminal no Admin. Se faltar, vale o `ref`. Não pode repetir a do balcão nem de outra extra. |
| `server_url` | não | se faltar, herda o do balcão. HTTPS obrigatório. |
| `agent_id` | não | só diagnóstico; se faltar, vira `<agent_id do balcão>-<ref>`. |
| `relay_poll_seconds` | não | se faltar, herda o do balcão (0,25 a 60). |

Config inválida faz o agente recusar subir com a mensagem do problema — rode
`--doctor` depois de editar para conferir antes de reiniciar.

Reinstalar o agente depois (`--install`) **preserva** `extra_printers`.

### 4. Reiniciar o serviço

```bash
systemctl --user restart nelson-pos-counter                         # Linux
launchctl kickstart -k gui/$(id -u)/com.nelson.pos-counter          # macOS
```

```bat
schtasks /end /tn "NelsonPosCounter" & schtasks /run /tn "NelsonPosCounter"
```

### 5. Conferir em `/health`

```bash
curl -s http://127.0.0.1:47811/health
```

Os campos de sempre continuam falando da impressora do balcão. A lista nova:

```json
"extra_printers": [
  {
    "ref": "cozinha-lanches",
    "queue": "Cozinha Lanches",
    "station_ref": "cozinha-lanches",
    "ok": true,
    "relay": {"state": "ok", "detail": "", "queue_health": "ready", "seconds_since_ok": 1.2}
  }
]
```

`state` é `starting` logo após subir, `ok` quando o último ciclo com o servidor
deu certo e `error` com o motivo em `detail` (ex. `servidor respondeu HTTP 401`
= credencial errada ou revogada). `queue_health` é a sonda da fila, refeita a
cada 30 s pela própria thread — o `/health` não sonda a impressora extra na
hora, para uma impressora de rede lenta não atrasar a resposta do balcão.
O `--doctor` também lista cada extra, com a fila e o resumo do journal.

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
