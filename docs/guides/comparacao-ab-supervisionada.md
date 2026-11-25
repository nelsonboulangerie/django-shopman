# Comparação A/B supervisionada da loja

Protocolo do OC-23 (Etapa III omnicanal, compromisso DEV-2026-085), que executa o §9.6 e
a parte pré-go-live do §7.4 do plano
[`docs/reports/2026-11-23-etapa-ii-omnicanal-espec-e-plano.md`](../reports/2026-11-23-etapa-ii-omnicanal-espec-e-plano.md).
Serve para decidir entre duas versões CORRETAS de uma tela (as candidatas B1 a B3 do §7.1,
que só existem depois da aprovação L2 do dono, no OC-33). Correção não se testa: os
invariantes X1 a X16 valem para as duas versões e não são variável de A/B.

Há duas metades: a **ferramenta**, que roda as mesmas jornadas nas duas versões e mede o
que dá para medir por máquina, e a **sessão humana**, que mede o que só uma pessoa diz.

## 1. A ferramenta (`make experience-compare`)

```bash
createdb shopman_ab                      # um banco SÓ desta comparação: o seed o apaga
DATABASE_URL=postgres://localhost:5432/shopman_ab \
  lockf /tmp/shopman-previa.lock make experience-compare
```

O que acontece (`scripts/run_experience_compare.sh`):

1. Compila a loja uma vez.
2. **Rodada A**: `seed --flush --profile qa` (loja aberta 24 h), os experimentos ligados
   pelo harness (`shopman/shop/tests/e2e/seed_experience.py`: o de prova, `prova-e2e`, e
   todos os que a loja anota com `EXPERIMENT(<ref>)` em `surfaces/storefront-nuxt/app`,
   como o `home-recompra-no-topo` do OC-33 B2) com a coorte `internal = CLI-005`, a pilha das jornadas de pé (`scripts/run_storefront_journeys.sh`)
   e as jornadas de `surfaces/storefront-nuxt/tests/e2e/journeys/` com a cliente CLI-003,
   que fica FORA da coorte: o servidor decide "a".
3. **Rodada B**: o mesmo seed, os mesmos experimentos com `internal = CLI-003`: a mesma
   cliente fica DENTRO, e o servidor decide "b" em todos. `EXPERIENCE_REFS="ref1,ref2"`
   restringe a lista.
4. O relatório junta as duas rodadas.

A versão nunca é escolhida pela URL, por cookie ou pelo teste (decisão D1). A primeira coisa
que cada rodada faz depois de a cliente entrar é ler o shell e reprovar se a versão não é
a esperada; cada jornada confere de novo antes de começar.

As jornadas são as do §5.1, escritas uma vez e iguais nas duas versões:

| Arquivo | Jornada |
|---|---|
| `01-informacao` | horário, endereço, pagamento, entrega e alérgenos em até dois toques |
| `02-retirada-hoje` | do cardápio ao acompanhamento, retirada hoje com Pix |
| `03-encomenda-outro-dia` | a fornada de amanhã, do produto ao acompanhamento |
| `04-entrega-fora-da-zona` | endereço a 14,8 km recusado antes do pagamento, troca para retirada |
| `05-pix` | código, copiar, prazo e o pagamento que chega sozinho |
| `06-acompanhar` | o pedido pago, aberto pela conta |
| `07-recompra` | "Repetir pedido" na home logada leva os itens à sacola |

Em cada passo, nas larguras 320, 375 e 390 px e no computador (1366 px):

- **captura** normal e com a fonte raiz a 200 % (X11);
- **axe** com as regras WCAG 2.2 AA (X10), sem a fita "Ambiente de desenvolvimento", que só
  existe fora de produção;
- **X9**: tamanho (mínimo 14 px) e contraste AA de cada elemento marcado `data-decisive`,
  e 16 px no corpo de leitura. É a MESMA medida da varredura da fila
  (`surfaces/storefront-nuxt/tests/journeys/support/typographyAudit.mjs`, OC-30). Tela sem
  nenhuma marcação aparece como "sem marcação", nunca como aprovada;
- **X11**: com a fonte raiz a 200 %, nenhuma ação nem decisivo some, sai da tela, é
  cortado ou fica embaixo de barra ou cartão fixo (a mesma medida, com `obscured`);
  rolagem lateral é achado;
- **shell** (X13): o contrato que a loja leu. O relatório mostra a diferença entre A e B
  no mesmo passo; a única esperada é `experience`.

A auditoria não reprova a jornada: ela é a medida. O que reprova é a jornada não chegar
ao fim ou o servidor decidir outra versão.

**Saída** (ignorada pelo git): `surfaces/storefront-nuxt/test-results/experience-compare/`,
com `relatorio.html` (no topo, a tabela de achados das duas versões; depois, por passo,
capturas lado a lado, axe, X9, X11, diferença do shell),
`relatorio.md` (o sumário para colar no PR) e, por versão, `a/` e `b/` com as capturas, o
`audit.json` de cada passo, o trace do Playwright e `rodada.json` (versão decidida pelo
servidor e hora da rodada).

**Relógio.** O estado aberto/fechado é fixo (o seed abre a loja 24 h), e o navegador roda
no fuso da loja. O relógio do servidor não é fixável sem tocar código de produção: A e B
rodam em sequência, e horários de janela podem diferir entre as duas rodadas. Perto da
meia-noite a loja não oferece mais retirada para hoje; rode de dia. Fixar o relógio do
servidor está na #3574; a encomenda com a loja fechada, na #3575.

**Achado conhecido.** Defeito que já tem issue aparece no relatório com o número, nunca
escondido: a exceção declarada pela própria medida (`data-x11-exception` e
`data-contrast-exception`, `<nome>-<issue>`, como o cartão do produto, #3590) e os achados
do axe listados em `KNOWN_FINDINGS` (`surfaces/storefront-nuxt/scripts/experience-compare.mjs`).
Quem conserta fecha a issue e tira a marca ou a linha. O que não tem issue sai como "novo".

**Portas.** A pilha usa as portas `JOURNEYS_*_PORT` de `scripts/run_storefront_journeys.sh`
e recusa subir com porta ocupada; numa máquina com outras sessões, passe portas próprias e
`JOURNEYS_LOG_DIR` próprio.

## 2. A sessão humana

**Preparação.** A pilha da ferramenta, de pé, num celular de teste (ou no navegador do
computador em 375 px). Gateway falso: o Pix é o simulado da pilha e o cartão é o Stripe
falso; nada de cobrança real. Mesmo seed e mesma hora do dia para todas as pessoas. A
versão de cada pessoa é decidida pelo servidor, pela allow-list da coorte (a cliente de
teste dentro ou fora), nunca por link.

**Perfis** (ao menos uma pessoa de cada, por versão):

| Perfil | Como entra |
|---|---|
| Pessoa idosa | o celular dela ou um igual, sem ajuste |
| Baixa visão | zoom do sistema a 200 % (fonte ampliada) |
| Pouca familiaridade digital | sem explicação prévia da loja |
| Experiente | usuária frequente de app de pedido |

**Ordem.** Cada pessoa faz as tarefas nas duas versões, com a ordem alternada entre
pessoas (metade começa por A, metade por B), para o aprendizado da primeira não favorecer a
segunda.

**Tarefas** (as mesmas jornadas da ferramenta, ditas em palavras de cliente):

1. "Descubra até que horas a padaria abre hoje e se ela entrega no seu bairro."
2. "Peça um croissant para buscar hoje e pague com Pix."
3. "Encomende uma Tabatière para amanhã."
4. "Peça para entregar na Estrada do Limoeiro, 10, Irerê." (fora da área)
5. "Pague o Pix do pedido que você fez."
6. "Veja em que pé está o seu pedido."
7. "Peça de novo o que você pediu da última vez."

**Pergunta de verificação**, ao fim de cada tarefa de pedido: *"Para quando é o seu pedido
e como vai pagar?"* A resposta é certa ou errada pelo que o pedido registrou.

**Medidas**, por pessoa, versão e tarefa:

| Medida | Registro |
|---|---|
| Concluiu sem ajuda | sim / com ajuda / não concluiu |
| Entendeu o compromisso | resposta da pergunta de verificação certa / errada |
| Erros | quantos e quais (toque errado, voltar, campo refeito) |
| Becos sem saída | telas de onde a pessoa não soube sair |
| Tempo | segundos, do primeiro toque ao fim |
| Toques | contagem |

O facilitador não ensina; quando a pessoa pede ajuda, a tarefa vira "com ajuda". Capturas
e trace das duas versões vão para o mesmo relatório da ferramenta.

## 3. Decisão

Segue o §7.4: amostra mínima por braço declarada antes da sessão; amostra abaixo do piso
é inconclusiva e não promove; a versão candidata passa os portões X1 a X16, melhora a
fricção que a hipótese mirou e não piora a experiente além do limite declarado. Quem
decide é o dono.
