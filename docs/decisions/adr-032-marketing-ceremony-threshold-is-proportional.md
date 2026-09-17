# ADR-032 — O limiar da cerimônia é proporcional à casa, e mede pessoas

**Status:** Aceito em 2026-09-17
**Sucede:** [ADR-031](adr-031-marketing-ceremony-proportional-to-consequence.md), que
mantém tudo o que disse sobre `fire`, `immediate` e agendamento. O que muda aqui são os
dois números que ela deixou no código, e a grandeza que eles mediam.

## Contexto

A ADR-031 fez a cerimônia medir a consequência e escreveu os limiares como constantes:
`CEREMONY_TYPED_THRESHOLD = 50` e `CEREMONY_DUAL_CONTROL_THRESHOLD = 500`. O dono revisou
e apontou dois defeitos, os dois reais.

**Um número absoluto só está certo para um tamanho de base.** O 50 era herdado: vivia na
condição antiga (`immediate or count >= 50`), nunca chegou a decidir nada, porque a
primeira metade da condição já escalava tudo. Ninguém o validou, e ele envelhece sozinho:
com 200 clientes, 50 pessoas é um quarto da casa e mesmo assim passa com um toque; com
20.000, 50 é 0,25% e a senha interrompe um disparo de rotina.

**Plataforma não é pessoa.** `_external_target_count` somava as duas grandezas — uma
pessoa alcançada por mensagem e um mural alcançado por postagem — e a política aplicava
um limiar à soma. "Três postagens" e "três pessoas" não são a mesma coisa: a mensagem
sai da casa, chega em quem não pediu aquele horário, custa por unidade e não volta; a
postagem fica num mural, não custa por pessoa e se apaga com um toque. Nenhum limiar
serve para as duas. Na prática, 498 pessoas + 2 postagens viravam "500 destinos" e
mudavam de faixa por causa de dois murais.

## Decisão

### 1. O limiar é uma proporção da casa, ou o gasto — o que chegar primeiro

Palavras do dono: *"estabeleço: 2% da base de clientes. Ou threshold para gasto, o que
chegar primeiro. ponto. Tudo ajustável via admin, claro."*

```
limiar (pessoas) = max(piso, min(⌈percentual × base⌉, teto_de_gasto ÷ custo_por_mensagem))
duplo controle   = limiar × múltiplo
```

- **base de clientes** = o cadastro **ativo** da casa (`Customer.is_active=True`), um por
  pessoa conhecida, já sem quem pediu para ser esquecido — a anonimização do guestman é
  exatamente o que desliga esse campo. Não é o público alcançável, que é sempre menor
  (precisa de telefone, consentimento verificado e maioridade declarada): o alcançável é
  o numerador, a base é o denominador. ⚠️ O histórico importado do Yooga **não** entra:
  `backstage/bi/ingest/yooga.py` escreve `HistoricalSale` e guarda `phone_hash` para um
  join que ainda não existe em código; quem só comprou no sistema antigo não tem cadastro.
  O Admin diz isso na tela, para o número não parecer um erro.
- **custo** — só mensagem direta custa (template de WhatsApp, cobrado por mensagem).
  Postagem pública não tem custo por pessoa e não entra na conta.
- **o piso é o lado fechado.** Base vazia, base absurdamente pequena ou banco mudo caem
  no piso, que pede cerimônia **mais cedo**. Não existe divisão pela base em lugar nenhum
  do cálculo, então não existe denominador zero para abrir a porta.
- **tudo no Admin** (Loja → Integrações → "Cerimônia do disparo"), em
  `Shop.defaults["marketing"]` — sem migração, sem deploy: percentual, teto de gasto,
  custo por mensagem, piso e o múltiplo do duplo controle. Ao lado dos campos, a tela
  mostra **a conta com os números de hoje**: quantas pessoas a base tem, quanto dá pela
  fatia, quanto dá pelo gasto, qual das duas venceu e onde cada faixa começa.

Padrões que entram no código como **padrão**, não como verdade:

| Ajuste | Padrão | Origem |
|---|---|---|
| percentual da base | 2% | decisão do dono, textual |
| teto de gasto | R$ 50,00 | ⚠️ palpite a confirmar |
| custo por mensagem | R$ 0,07 | ⚠️ palpite a confirmar — o preço real está no contrato com Meta/ManyChat e muda por categoria de modelo; fica arredondado para cima de propósito, porque custo superestimado faz o teto morder antes, nunca depois |
| piso | 10 pessoas | ⚠️ palpite a confirmar |
| múltiplo do duplo controle | 10× | preserva a razão 50→500 da política anterior |

Com 2.500 clientes, esses padrões reproduzem exatamente os números antigos: 50 e 500. A
diferença é que agora eles são consequência de um tamanho de casa, e não de um número que
ninguém validou.

### 2. Dois eixos, duas contagens, dois nomes

Uma função por grandeza, e o nome diz qual:

- `direct_message_recipient_count` — **pessoas** que recebem mensagem. É a grandeza
  irreversível e cobrada, e é a única que decide cerimônia.
- `public_post_count` — **plataformas** em que o anúncio vira postagem.
- `external_destination_count` — a soma das duas, que continua existindo e continua
  somando, porque é a grandeza da **quota diária de 5.000 destinos** e do **teto de 5.000
  por comando**. Ali a pergunta é outra — "quanto deste comando sai da casa hoje" — e uma
  postagem ocupa a API da plataforma tanto quanto uma mensagem ocupa a do WhatsApp.
  Somar pessoa com plataforma está certo para contabilizar volume e errado para medir
  risco.

Daí:

- **mensagem** — a cerimônia escala com o número de pessoas, pela regra acima;
- **postagem** — pede sempre só o resumo, qualquer que seja o número de plataformas;
- **disparo misto** — manda a parte de mensagem, porque é a irreversível;
- a obrigação de agendar acima de 2.000 passa a contar **mensagens**
  (`LARGE_BLAST_SCHEDULE_THRESHOLD`), pelo mesmo motivo.

A frase digitada passa de `PUBLICAR <destinos>` para `ENVIAR <pessoas>`: ela só existe no
eixo de mensagem, e descreve o que vai acontecer com o nome que a casa usa.

### 3. A prévia do cockpit passou a saber de que eixo se trata

`shopman/backstage/projections/marketing_actions.py` resolvia a confirmação **sem passar
as plataformas**, e o servidor caía no caminho conservador: contava o público elegível
como se fosse destinatário. Um anúncio só de postagem prometia na tela a cerimônia de
centenas de pessoas. Agora a projeção passa `platform_refs`, e prévia e comando
respondem a mesma coisa.

## Consequências

O que muda para quem opera: o ritual volta a acompanhar o tamanho da casa. Numa casa de
2.500 clientes, 300 mensagens pedem frase e senha; numa de 100.000, o mesmo disparo passa
com o resumo — e lá o limiar são 714 pessoas, porque o teto de gasto chega antes da
fatia. Postagem nunca pede senha.

O risco aceito é explícito e tem nome: **os padrões de gasto, custo e piso são palpites**
até o dono confirmar o contrato com a Meta/ManyChat e o que a casa aceita gastar num
disparo. Enquanto forem palpites, quem decide é o Admin, e a tela mostra a conta inteira
para que a conferência seja de olho, não de fé.

A base cacheada dura 60 segundos e é invalidada na hora por qualquer escrita em
`Customer` (`post_save`/`post_delete` em `marketing_security_signals.py`). Cache de regra
de uma hora já custou caro nesta casa; aqui a mentira mudaria se a tela pede senha ou não,
então o cache curto existe só para a projeção do cockpit não fazer um `COUNT` por ação.

Nada mais foi afrouxado: RBAC, token de uso único, CAS por versão, idempotência,
comprovante, congelamento de emergência, quota durável de 5.000 destinos externos por dia,
teto de 5.000 destinos por comando e a obrigação de agendar continuam como estavam.

## Referências

- `shopman/shop/marketing_policy.py` — `MarketingPolicy.ceremony_threshold`
- `shopman/shop/services/marketing_ceremony.py` — a base viva e o cache
- `shopman/shop/services/marketing_security.py` — `requirement_for` e as três contagens
- `shopman/shop/tests/test_marketing_ceremony.py`, `shopman/shop/tests/test_marketing_security.py`
- `docs/reference/marketing-surface-contract.md`
