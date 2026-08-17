# Agente do balcão

Processo local, sem dependências, que recebe um pedido do PDV em `127.0.0.1` e
entrega bytes crus à impressora térmica pelo spooler: o kick ESC/POS que abre a
gaveta e o papel que o servidor compôs (comprovante de movimento de caixa hoje,
DANFE NFC-e depois — obrigação legal). Ele é a ponte do navegador com o hardware
do balcão; a gaveta é um dos aparelhos que ele alcança, não o escopo dele.

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
  "allowed_origins": ["https://pdv.boulangerie.com.br"]
}
```

Só fatos **da máquina**. O pulso e a política (adapter, abrir-na-venda) moram no
Django, por terminal, e chegam no request — para não existirem dois donos da
mesma resposta.

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

## Segurança

CORS não protege endpoint com efeito colateral — um `POST` simples *chega* aqui
mesmo com a resposta bloqueada pelo navegador. Quem protege é o **token**; a
allowlist de origem é a segunda tranca. Sem token, qualquer aba aberta no balcão
abre a gaveta de dinheiro.

O agente escuta só em loopback. Não exponha na rede.

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

## Testes

```bash
python3 -m pytest tools/pos-counter-agent/test_counter_agent.py -v
```
