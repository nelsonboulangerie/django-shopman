# Agente da gaveta de dinheiro

Processo local, sem dependências, que recebe um pedido do PDV em `127.0.0.1` e
manda o kick ESC/POS para a impressora térmica pelo spooler.

**Por que ele existe:** a gaveta não tem cabo próprio — ela pendura no RJ11 da
impressora e abre quando a impressora recebe `ESC p m t1 t2`. O PDV roda no
navegador, e navegador não fala ESC/POS. Como a TM-T20 é USB e o driver do
sistema já é dono da interface, WebUSB está fora (brigar pela interface quebraria
a impressão do recibo). Sobra entregar os cinco bytes ao **spooler**, pela mesma
fila por onde o recibo já sai.

Desenho e alternativas descartadas: [POS-CASH-DRAWER-PLAN](../../docs/plans/POS-CASH-DRAWER-PLAN.md).

## Instalar (Linux, systemd --user)

**Comece pelo Admin**, não por aqui: Terminais do PDV → o balcão → *Baixar o
agente e ver como instalar*. Aquela tela entrega o arquivo e o comando **já
preenchido** com o token, a fila e a origem daquele terminal. Nada a transcrever.

É **um arquivo só** — `drawer_agent.py`. Leve até o balcão por qualquer meio
(pendrive, `scp`, ou colando num editor) e rode o comando que a tela mostrou:

```bash
python3 drawer_agent.py --install --token TOKEN-DO-ADMIN --origin https://pos.staging.nelsonboulangerie.com.br
```

Ele lista as filas CUPS e pergunta qual é a da térmica (a fila já existe: é por
ela que o recibo imprime hoje). Passe `--queue` para não ser perguntado.

**Sem `--token`** ele gera um e imprime na tela para você colar no Admin. É o
caminho de emergência, para quem estiver no balcão sem acesso ao Admin — o
normal é o Admin ser o dono do par.

Reinstalar preserva o token guardado; só um `--token` diferente rotaciona. O PDV
levaria 401 até os dois lados baterem, e ninguém quer descobrir isso no sábado.

## Config

`~/.config/nelson-pos-drawer/agent.json`, modo 600:

```json
{
  "queue": "TM-T20",
  "token": "…",
  "port": 47811,
  "host": "127.0.0.1",
  "allowed_origins": ["https://pos.staging.nelsonboulangerie.com.br"]
}
```

Só fatos **da máquina**. O pulso e a política (adapter, abrir-na-venda) moram no
Django, por terminal, e chegam no request — para não existirem dois donos da
mesma resposta.

## API

| rota | corpo | resposta |
|---|---|---|
| `POST /kick` | `{token, reason, pulse:{pin,on_ms,off_ms}}` | `{ok, queue, job_id}` |
| `GET /health` | — | `{ok, accepting, queue, reason, version}` |

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
systemctl --user status nelson-pos-drawer
```

```bash
journalctl --user -u nelson-pos-drawer -f
```

Cada kick vira uma linha (`kick OK motivo=… fila=… job=…`). O journal é a
verdade **física** do balcão; o servidor só sabe o que a tela mandou.

Testar o caminho até o spooler sem navegador:

```bash
python3 ~/.local/share/nelson-pos-drawer/drawer_agent.py --kick
```

## Testes

```bash
python3 -m pytest tools/pos-drawer-agent/test_drawer_agent.py -v
```
