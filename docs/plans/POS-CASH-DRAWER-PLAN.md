# POS-CASH-DRAWER-PLAN — o caminho que abre a gaveta

**Status:** em execução (2026-08-12). Nasce da seção 2 do
[POS-HARDWARE-READINESS-HANDOFF](POS-HARDWARE-READINESS-HANDOFF.md), que
diagnosticou o problema e descartou dois caminhos. Este plano constrói o
terceiro.

**Aparelho:** Epson TM-T20, USB, rolo de 80mm. ESC/POS nativo; o kick é
`ESC p m t1 t2` → `1B 70 00 19 FA` (m=0 → pino 2; pulso 25ms ligado / 250ms
desligado).

**Máquina do balcão:** Linux, **um** terminal (respondido pelo Pablo,
2026-08-12). CUPS, portanto `lp -o raw`. A config nasce por terminal mesmo com
um só, porque um segundo balcão não pode obrigar a mexer em código.

---

## 1. A pergunta que vinha antes de tudo: HTTPS → localhost

A página do PDV é HTTPS (`pdv.boulangerie.com.br`) e o agente é
local. Se o navegador bloqueasse essa chamada, o desenho inteiro mudava.

**Medido no Chrome 148, de uma origem HTTPS pública para `http://127.0.0.1`:**

| caso | resultado |
|---|---|
| `GET` simples | **200** — sem preflight |
| `POST` `text/plain` (CORS-simple) | **200** — sem preflight |
| `POST` `application/json` (com preflight) | **200** |
| preflight com o servidor **omitindo** `Access-Control-Allow-Private-Network` | **200** — não é exigido |
| `Access-Control-Request-Private-Network` no preflight | **nunca apareceu** |

Loopback continua sendo *potentially trustworthy origin*: não é mixed content, e
o Local/Private Network Access não está sendo cobrado nesta versão.

**Consequência:** o desenho simples se sustenta. **Não** precisamos de TLS com
certificado local no agente, nem do desvio pelo backend via `Directive` — que
custaria uma volta à DO e de volta no exato momento em que o operador está com a
mão esperando a gaveta.

**A margem que guardamos:** o agente responde
`Access-Control-Allow-Private-Network: true` no preflight mesmo sem ninguém
pedir. É um header de uma linha, inerte hoje, e é exatamente o que passa a ser
exigido se o Chrome religar a cobrança de PNA.

> ⚠️ O que isso **não** prova: se um dia o Chrome ligar o *permission prompt* de
> Local Network Access, um header não resolve — vira consentimento do usuário,
> uma vez, no kiosk. É risco conhecido e mitigável, não desconhecido.

## 2. Quem é dono de quê

O erro fácil aqui é a config existir em dois lugares e divergir
(`feedback_one_question_one_owner`). O corte:

| fato | dono | por quê |
|---|---|---|
| nome da fila CUPS, porta, token, origens | **agente local** | fatos da máquina do balcão; o servidor na DO não tem como saber |
| adapter (`manual`/`agent`), endereço do agente, pulso, abrir-na-venda | **Django** (`POSTerminal`) | é política da loja, e o dono configura pelo Admin |

O pulso viaja no request. O agente **não tem** pulso configurável — ele aplica o
que recebe. Assim não existe "o pulso do Django" e "o pulso do agente" para
discordarem.

## 3. O agente (`tools/pos-counter-agent/`)

Python 3 da stdlib, zero dependências, HTTP em `127.0.0.1`.

- `POST /kick` — `{token, reason, pulse:{pin,on_ms,off_ms}}` → monta
  `ESC p m t1 t2` e manda como **job raw** (`lp -d FILA -o raw`). Responde
  `{ok, queue, job_id}`.
- `GET /health` — sonda **de verdade**: pergunta ao CUPS se a fila existe e se
  está aceitando trabalho (`lpstat`). Responde `{ok, queue, accepting, reason}`.

**Segurança.** CORS não protege endpoint com efeito colateral: um `POST` simples
*chega* ao servidor mesmo com a resposta bloqueada. Então a defesa real é o
**token**, e a allowlist de origem é a segunda camada. Sem isso, qualquer página
aberta no navegador do balcão abre a gaveta de dinheiro.

**Honestidade da sonda.** `lpstat` prova que a fila existe e aceita — **não**
prova que a gaveta está plugada no RJ11 nem que ela abriu. A TM-T20 sabe
responder o estado do pino, mas a resposta exige leitura bidirecional, que um
job de spool não dá. Por isso o teste de gaveta termina com o operador
confirmando com o olho: *"abriu?"*. Sonda que mente é pior que sonda que falta.

## 4. O health do terminal, honesto

A seção 4 do handoff acusa `_component_health` de ser declaração fantasiada de
sonda. A correção tem um detalhe que muda o desenho: **o Django nunca vai poder
sondar o agente** — o agente está na loopback do balcão e o servidor está na DO.
Só o navegador do balcão alcança.

Portanto: com `adapter: "agent"`, o status do servidor é `deferred` — "verificado
na estação" —, e quem preenche é a superfície, que sonda o `/health` e mostra o
resultado. Marcar `ready` do lado do servidor seria repetir a mentira, só que com
outro nome.

## 5. Os quatro momentos

Um caminho só (`useCashDrawer`), quatro chamadas:

| momento | onde | autorização |
|---|---|---|
| venda em dinheiro | `submitSale()`, após o `ok`, se houver tender `cash` | a venda já é o registro |
| sangria | `registerCashMovement()`, após o `ok` | PIN de gerente (política já no `main`) |
| suprimento | idem | a do movimento |
| abrir sem venda | botão na antesala → `POST pos/cash/drawer-open/` | `operate_pos` + motivo obrigatório |

**Abrir sem venda é o único que não deixa rastro sozinho** — não há venda nem
movimento para contar a história. Por isso passa pelo servidor antes de chutar:
grava quem, quando e por quê como evento `drawer_opened` no log do PDV
(`backstage.POSEvent`, append-only). Nasceu numa lista em
`CashShift.metadata`; migrou quando o log unificou os rastros do caixa (ver
`docs/reference/data-schemas.md#posevent-payload`).

⚠️ **O que este plano NÃO decide:** quem pode abrir. A frente de estresse do PDV
já resolveu que retirada exige PIN em qualquer valor, e isso está no `main`. Aqui
é o caminho físico. Exigir um motivo é substância da auditoria, não portaria.

## 6. Fora de escopo, de propósito

**Comprovante impresso de sangria.** É valioso — é a testemunha física que a
política de PIN queria — mas é item separado. Se o comprovante virar o jeito de
abrir a gaveta, volta o acoplamento que o handoff descartou: sangria só abriria a
gaveta se alguém lembrasse de imprimir.

## 7. O pulso não é 25/250ms — é 50/500ms

Achado durante a implementação, e vale corrigir onde estiver escrito.

A sequência canônica `1B 70 00 19 FA` tem `0x19` = 25 e `0xFA` = 250, mas esses
são **unidades de 2ms**. O pulso real é **50ms ligado / 500ms desligado**.
Descrever como "pulso 25/250ms" é atalho comum e erra pela metade — e teria
virado o default da config, mandando ao solenoide metade do pulso que o manual
pede. Os testes travam o default nos bytes canônicos, dos dois lados.

## 8. O que foi verificado, e como

| o quê | como |
|---|---|
| HTTPS → loopback não é bloqueado | Chrome 148, `fetch` de origem HTTPS pública; 5 casos (tabela §1) |
| os cinco bytes chegam ao spooler | agente real + `lp` dublê; capturado `1b 70 00 19 fa` com `-d FILA -o raw` |
| a página HTTPS fala com o agente | `POST /kick` de `https://example.com` → 200; sem token → 401 |
| config persiste e valida | Admin real: `agent` sem token **recusado**; com token, gravado em `metadata.hardware.cash_drawer` |
| health vira `deferred` | `runtime_profile` do terminal salvo; badge geral segue `ready` |
| abrir sem venda | botão "Troco" no PDV → trilha `{by: admin, reason: Troco}` → kick `no_sale` no spooler |
| suprimento abre a gaveta | "Registrar movimento" → kick `suprimento` no spooler |
| a sonda não promete demais | "Fila TM-T20 respondendo. A gaveta abriu?" |
| suítes | 20 (agente) + 22 (Django) + 199 (pos-nuxt) + 1021 (backstage) + `make admin`; typecheck limpo |

⚠️ **O que continua sem prova:** a impressora. Falta, no balcão: instalar o
agente, e o olho do operador confirmando que a gaveta abriu.

> ❌ **Correção (2026-08-13): "no Mac não dá" estava ERRADO.** Ver §12. O CUPS do
> macOS entrega os bytes crus normalmente; o que a Apple removeu foi outra coisa.

## 9. Ordem

1. ~~Agente + testes~~ ✅
2. ~~`CashDrawerConfig` + Admin + health honesto~~ ✅
3. ~~Endpoint auditado de abrir sem venda~~ ✅
4. ~~Os quatro momentos na superfície + teste de gaveta na antesala~~ ✅
5. **No balcão:** baixar o agente pelo Admin, rodar o comando que a tela mostra,
   apertar "Testar gaveta". É o único passo que sobra, e ele precisa do aparelho.

> O agente é **um arquivo só**, de propósito: é o que uma pessoa consegue levar
> até o balcão por qualquer meio — pendrive, `scp`, ou colando num editor. Dois
> arquivos que precisam chegar juntos são uma chance a mais de chegar só um.

## 10. O Admin entrega o agente (2026-08-12)

O dono já está no Admin configurando o terminal. Mandá-lo caçar um arquivo no
repositório para completar a tarefa é atrito bobo, então a tela
`/admin/pos/terminal/<ref>/agent/` entrega o arquivo e as instruções.

**O token inverteu de dono.** Antes nascia no instalador e alguém transcrevia 43
caracteres de um terminal Linux para o formulário — erro que só aparecia como
401 na hora de dar troco. Agora o **Admin gera** e o comando sai pronto com ele
dentro; o instalador aceita `--token`. Rotação é explícita (uma caixa "Gerar um
token novo"), porque trocar sozinho derrubaria a gaveta do balcão sem aviso.

⚠️ **`tools/` não ia na imagem do deploy** — o Dockerfile copiava só `config`,
`packages` e `shopman`. Sem o `COPY tools`, o download funcionaria local e daria
404 no staging. Se um dia voltar a quebrar só em produção, é a primeira linha a
conferir; a tela também diz isso em vez de estourar 500.

O token viaja no comando e aparece na tela do Admin. É deliberado: ele não abre
nada além da gaveta daquele balcão, e o custo de errar a transcrição era maior.

## 11. ⚠️ O domínio do PDV é `pdv.boulangerie.com.br`

Conferido no spec LIVE da DO (2026-08-12): `SHOPMAN_POS_BASE_URL =
https://pdv.boulangerie.com.br`, e o ingress casa a autoridade exata
`pdv.boulangerie.com.br` para o serviço `pos-nuxt`.

As superfícies de **operador** vivem em `boulangerie.com.br` (`pdv`, `gestor`,
`kds`, `prod`, `central`, `mkt`, `api`); a **loja** e a API dela vivem em
`staging.nelsonboulangerie.com.br`. São dois domínios, com propósitos diferentes.

**O agente tinha um domínio inventado cravado** (`pos.staging.nelson…`), que não
existe em lugar nenhum. Instalar sem `--origin` teria dado **403 calado** na
gaveta. O constante saiu: sem `--origin`, a allowlist fica **vazia** (aceita
qualquer origem, com o token ainda obrigatório) e o instalador avisa em voz alta.
Quem sabe a origem é o Django, e o Admin já a injeta no comando.

Um teste proíbe qualquer domínio de deployment dentro do agente — ele é
genérico, e constante inventada em arquivo que ninguém revisa vira defeito
silencioso no balcão.

### Se o operador reclamar da distância

O botão de abrir sem venda mora na antesala do caixa, junto com sangria e
suprimento. Se na prática ele fizer falta na tela de venda, promover é barato: o
`useCashDrawer` já é compartilhado, e a tela de venda só precisa chamar o mesmo
`openDrawerWithoutSale`. Não fizemos agora para não inventar affordance sem
alguém tendo sentido falta.

## 12. Os três sistemas (2026-08-13)

O balcão **vai ser Linux** — é o oficial, e nada disso muda essa decisão. Mas a
máquina do caixa **ainda roda Windows**, e a troca não pode ser feita com a loja
aberta; e o dono precisa conseguir testar do Mac dele. Então o agente passou a
falar os três, e a tela do Admin ganhou um seletor.

### ❌ A correção: eu disse que no Mac não dava, e estava errado

A afirmação anterior ("macOS removeu suporte a fila raw, é justamente o
mecanismo") nasceu de **uma mensagem de erro lida rápido demais**:

```
$ lpadmin -p fila -v socket://… -m raw
lpadmin: Filas brutas não são mais compatíveis com o macOS.
```

Isso recusa criar fila com o **driver** `raw`. A **opção de job** `-o raw` é
outra coisa, e continua existindo. Numa fila sem driver, ela entrega os bytes
sem tocar. **Medido** (CUPS 2.3.4, macOS, fila apontando para um socket local):

```
RECEBIDO: 1b 70 00 19 fa
```

Os cinco bytes, intactos. O erro de método foi concluir a partir do que a
ferramenta **recusou**, em vez de testar o que eu precisava saber.

### O que muda por sistema (menos do que parece)

| | envio dos bytes | início automático | registro |
|---|---|---|---|
| **Linux** (oficial) | `lp -o raw` | systemd `--user` + linger | journald |
| **macOS** | `lp -o raw` — **idêntico** | LaunchAgent (`KeepAlive`) | arquivo |
| **Windows** | winspool via `ctypes`, datatype `RAW` | tarefa no logon (`pythonw`) | arquivo |

Linux e macOS são o **mesmo** caminho de envio. Só o Windows troca o mecanismo —
e ainda assim a linha que a pessoa digita é a mesma, fora o nome do interpretador.

⚠️ **O log em arquivo não é enfeite.** No Linux o journald captura a saída; no
macOS o launchd descarta, e no Windows o `pythonw` roda sem console. Sem o
`--log-file` que o instalador passa nesses dois, a promessa da tela ("o agente
registra cada abertura") seria falsa em dois dos três sistemas.

⚠️ **O Windows não foi executado em Windows nenhum.** Não há máquina aqui. O que
os testes travam é o despacho e o contrato; o `winspool` real só o caixa
confirma. O `ctypes` evita `pywin32` porque o balcão não é lugar de
`pip install` às 6h da manhã — mas o Windows também **não traz Python de
fábrica**, e a tela avisa isso no passo da instalação.
