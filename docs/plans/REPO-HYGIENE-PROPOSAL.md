# Proposta: arrumar a casa no endereço novo

**Estado:** §1a e §2 **decididos e/ou executados** em 18/08; o resto aguarda.
**Contexto:** o repo saiu de `pablondrina/django-shopman` para
`nelsonboulangerie/django-shopman` para habilitar a fila de merge. Endereço novo
é bom momento para estabelecer o que ficou implícito até aqui.

**Como ler:** uma seção por assunto, cada uma com o estado medido, uma
recomendação e o custo. O que já foi decidido está marcado; o resto é proposta.
Corte o que não quiser.

---

## 0. O que já mudou hoje (contexto, não proposta)

| | |
|---|---|
| repo | `nelsonboulangerie/django-shopman` (URL antiga redireciona) |
| fila de merge | **ativa** — testa o resultado do merge antes de aplicar |
| `strict` | **desligado**, a fila o tornou redundante |
| `Testes (test-backstage)` | não-obrigatório (6 de 9 PRs de 18/08 não tocavam backstage) |
| `migrate` de banco zerado | virou obrigatório (PR #200) |

Isso resolveu a esteira que custou 3 rodadas ao #197 e 3 ao #196.

---

## 1. Segredos e arquivos que nunca deveriam vazar

### O que eu medi

**Boa notícia: nenhum segredo real no histórico.** Varri todas as revisões:

- arquivos de credencial já commitados: só `.env.example` (2 variantes) e a
  matriz de credenciais — todos por desenho, sem valor;
- `sk_live_` (8 ocorrências) e `whsec_` (19): **todas** são doc descrevendo
  formato, fixture de teste (`sk_live_shopman…`), ou o próprio guarda que
  DETECTA chave viva (`integration_readiness.py`: `startswith("sk_live_")`);
- `BEGIN PRIVATE KEY`, `AKIA`, `ghp_`, `github_pat_`: **zero**.

**Duas lacunas reais:**

1. **`secret_scanning` do GitHub estava DESLIGADO** — os cinco: scanning,
   push protection, padrões não-provedor, validity checks, e o Dependabot.
   Em repo **público** é gratuito. (Resolvido em 18/08 — ver 1a.)
2. **`.gitignore` cobre `.env` e `.secrets/`, mas NÃO cobre `*.pem`, `*.p12`,
   `*.pfx`, `*.key`.** O certificado da Efí é exatamente um `.p12`/`.pem`. Hoje
   a proteção é uma frase em prosa no runbook ("Nao commite `.p12`…"), não uma
   regra.

### Recomendação

**1a. ✅ FEITO (18/08).** `secret_scanning` e `secret_scanning_push_protection`
**ligados**. Push protection recusa o push que contém segredo reconhecível
**antes** de ele existir no histórico — a única hora em que dá para consertar de
graça; depois o conserto é rotacionar a credencial, não apagar o commit.
O scan do histórico completo retornou **0 alertas**, confirmando a varredura
manual.
*Não ficaram ligados:* `non_provider_patterns` e `validity_checks` — são
Advanced Security, que o plano público gratuito não expõe. Os dois que importam
estão de pé.

**1b. Fechar o `.gitignore`** com `*.pem`, `*.p12`, `*.pfx`, `*.key`,
`*.jks`, `*.keystore`, e `.env.*` com exceção explícita para `.env.example`.
*Custo:* zero. *Recomendo.*

**1c. Um teste que trave o padrão**, no espírito da casa (regra que grita em
vez de prosa que se esquece): falha se algum caminho rastreado casar com os
padrões acima. É o que já se faz com `format_html` e com o gate canônico do
Unfold.
*Custo:* ~20 linhas. *Recomendo.*

---

## 2. Versionar pra valer

### O que eu medi

Existem 8 tags, **todas** `arquivo/<branch>` — marcadores de branch arquivada,
não versão. **Zero releases.** Ou seja: hoje não há versionamento, há histórico.

### O problema de aplicar SemVer aqui como se fosse biblioteca

Este repo não é uma biblioteca com consumidores externos. É um monorepo que
serve **uma casa**: 11 pacotes, 3 apps Django, 7 apps Nuxt, um deployment. Não
há ninguém "preso na 1.x". Então `MAJOR.MINOR.PATCH` no sentido clássico
(quebra de API pública) não tem a quem proteger.

O que existe de verdade aqui, e o que dói quando muda, é outra coisa:

- **migração de banco** (não dá para voltar sem plano);
- **contrato de payload** (`Session.data`, `Order.data`, `Directive.payload`) —
  directive já enfileirado com a chave antiga para de ser entendido;
- **contrato de projection** que uma superfície Nuxt consome;
- **vocabulário do operador** (o que está impresso, o que ele fala).

### Decisão do Pablo (18/08): **versão é rótulo do que está no ar**

Não é promessa de compatibilidade — não há a quem prometer. É a resposta para
"o que exatamente está rodando no staging agora?", que hoje só se responde
lendo SHA de deploy.

**Formato: `v<AAAA.MM.DD>`**, com sufixo `.N` quando houver mais de um release
no mesmo dia (`v2026.08.18`, `v2026.08.18.2`). Data é o rótulo certo para
"o que está no ar" — número sequencial exigiria decidir toda vez se aquilo é
MINOR ou PATCH, decisão que não serve a ninguém aqui.

**A tag nasce no deploy, não no merge.** Merge é intenção; deploy é fato. Uma
tag que existe sem estar no ar mente sobre o que ela é.

**O release carrega o que a versão não consegue dizer** — e é aqui que mora o
valor real, hoje espalhado em memória e corpo de PR:

```markdown
## ⚠️ Exige ação humana
- migração de dados / comando a rodar / variável nova / recadastro em provedor
  (ou: "nenhuma")

## O que muda para quem opera
(em português de operador, não de commit)

## Como voltar
```

O `v2026.08.18` de hoje, por exemplo, teria dito: *"o webhook da Efí passa a
aceitar `?token=`; recadastrar a URL na Conta Efi quando o PIX sair do mock"* —
que é exatamente a informação que hoje só existe porque eu escrevi na memória.

**Retroativo:** não. A primeira tag é a próxima subida. Inventar versão para o
passado seria arqueologia sem consumidor.

**As 8 tags `arquivo/*` existentes ficam** — são marcador de branch arquivada,
não versão, e não colidem com o formato `v*`.

---

## 3. Política de migração

### O que eu medi

Em 18/08 houve **duas colisões de número no mesmo dia** (`backstage/0019` e
`0020`), ambas porque o `main` andou entre numerar e empurrar.

O veneno não é a colisão, é a **invisibilidade**: nenhum teste verde a acusa,
porque a suíte roda sobre o estado do *branch*, e o branch é coerente consigo
mesmo. O conflito só existe na árvore que o **merge** produz.

### O que já está resolvido

- **A fila de merge revalida contra o alvo real.** Como o
  `makemigrations --check` já é obrigatório (job `Quality + deploy contract`),
  `multiple leaf nodes` passa a reprovar **na fila**, que é o lugar certo.
- **O PR #200** acrescentou o `migrate` de banco zerado ao mesmo job. O
  `makemigrations --check` valida o *grafo*; ele não prova que as migrações
  **aplicam** em ordem. A distinção é da sessão que levou as duas colisões, e
  está certa.

### Recomendação

**3a. Escrever a política em ADR**, curta, com três regras:
1. número sequencial permanece — o problema nunca foi o esquema de nome;
2. **nunca renumerar automaticamente** (esconde a colisão em vez de mostrá-la),
   **nunca trocar por timestamp** (troca um nome legível por ilegível para
   resolver um problema que não era de nomenclatura);
3. antes de abrir PR com migração: `make test-migrations` local; a fila
   confirma contra a árvore do merge.

**3b. Registrar a higiene de coordenação** que custou mais tempo que a esteira:

> `git diff origin/main..HEAD` **mente** — mostra diferença nos dois sentidos,
> listando como seu o que o `main` mudou. Deu 8 falsos positivos para duas
> sessões diferentes no mesmo dia. O certo:
> ```
> BASE=$(git merge-base HEAD origin/main)
> comm -12 <(git diff --name-only $BASE HEAD | sort) \
>          <(git diff --name-only $BASE origin/main | sort)
> ```

*Custo:* um ADR curto. *Recomendo.*

---

## 4. ADRs

### O que eu medi

21 ADRs, `adr-001` a `adr-021`, numeração sem buraco, nomes descritivos em
kebab-case. **Está mais organizado do que a maioria dos repos.**

O que falta não é reorganizar, é **navegar**:
- não há índice; para saber se existe ADR sobre um assunto, é `ls` e adivinhar
  pelo nome;
- não há campo de status — quais foram superados? O ADR-015 descreve política
  pós-produção que **ainda não vale** (pré-go-live), e isso não está visível;
- o [CLAUDE.md](../../CLAUDE.md) referencia ADRs individuais, mas nada aponta
  para o conjunto.

### Recomendação

**Não renumerar nada.** Renumerar ADR quebra toda referência existente (código,
CLAUDE.md, corpo de PR) para ganhar estética. Em vez disso:

**4a.** `docs/decisions/README.md` com tabela: número, título, status
(`aceito` / `superado por N` / `dorminhoco`), e uma linha do que decide.
**4b.** Cabeçalho de status nos 21 — mecânico, e faz o ADR-015 dizer
"vale a partir do `go-live-v1`" em vez de o leitor descobrir na §.

*Custo:* algumas horas, quase todo de leitura. *Recomendo o 4a; o 4b é opcional.*

---

## 5. Template de PR e recados

### O que eu medi

**Não existe `PULL_REQUEST_TEMPLATE`.** A qualidade do corpo dos PRs hoje
depende de quem escreve — e há PRs excelentes e PRs de uma linha no mesmo repo.

### Recomendação

Template curto, com as perguntas que **este** projeto aprendeu a fazer:

```markdown
## O que muda, e por quê

## ⚠️ Exige ação no deploy?
- [ ] migração  - [ ] comando a rodar  - [ ] variável nova  - [ ] recadastro em provedor
(se algum marcado, descreva EXATAMENTE o passo)

## Contrato que muda
- [ ] payload de Directive/Session/Order  - [ ] projection consumida por superfície
- [ ] vocabulário que o operador vê ou que sai impresso

## Como foi provado
(o par falha/passa de cada teste novo)
```

A terceira seção é a regra da casa que mais rende: teste que passa nas duas
pontas não prova nada. A segunda existe porque "o que exige ação humana" já se
perdeu antes.

*Custo:* um arquivo. *Recomendo.*

---

## 6. Nomenclatura

### O que eu medi

As convenções existem e são seguidas — `ref` não `code`, centavos com `_q`,
rota em inglês, chave de projection em inglês. Estão no
[CLAUDE.md](../../CLAUDE.md), que é lido.

Em 18/08 varri identificadores em português no código Python: 46 nomes, 181
ocorrências. Ficaram 21 arquivos corrigidos; 9 saíram por sessão concorrente.

**O que sobrou por decisão, e vale registrar como regra em vez de deixar como
julgamento repetido:**
- `cpf`, `cnpj`, `cep` **ficam** em português: são nome próprio de documento
  brasileiro, igual `IBAN`. `is_valid_cpf` é o nome certo;
- **prosa fica em português** (docstring, comentário, mensagem ao operador). A
  regra é sobre identificador, não sobre a língua da casa;
- nome de campo em API de terceiro **fica como o terceiro chama** e morre na
  porta de entrada. O `valor` da Efí é o caso canônico: sobrevive em
  `pix_item["valor"]`, e para dentro é `amount`.

### Recomendação

Três linhas no CLAUDE.md com o acima. *Custo:* minutos. *Recomendo.*

⚠️ **Pendência conhecida:** o `MovementType` do caixa
(`SANGRIA`/`SUPRIMENTO`/`AJUSTE`) segue em português. Não é esquecimento: o
valor está gravado no banco, aparece no comprovante **impresso**, e é o que o
operador fala. A casa já resolveu esse padrão antes (*comanda* na tela,
`POSTab` no código), então converter é coerente — mas é WP próprio, com migração
de dados, e passa por 3 apps Nuxt.

---

## 7. O que eu NÃO recomendo

- **Reescrever histórico** (`filter-repo`) para "limpar". Não há segredo real
  para remover, e reescrever invalida todo SHA em PR, memória e doc.
- **Renumerar ADR ou migração.** Quebra referência para ganhar estética.
- **SemVer clássico** como promessa de compatibilidade. Não há destinatário.
- **Squash obrigatório.** O histórico atual conta a história em commits
  legíveis, com o *porquê* na mensagem. Squash apagaria isso.

---

## Ordem sugerida

| # | item | custo | por que primeiro |
|---|---|---|---|
| 1 | ~~secret scanning + push protection~~ ✅ · `.gitignore` pendente | minutos | é o único com janela: segredo que entra não sai de graça |
| 2 | template de PR | minutos | rende em todo PR seguinte |
| 3 | ADR de política de migração + higiene de coordenação | 1h | a dor é de hoje, e a memória está fresca |
| 4 | três linhas de nomenclatura no CLAUDE.md | minutos | fecha julgamento repetido |
| 5 | índice de ADRs | horas | qualidade de vida |
| 6 | versionamento | primeiro deploy | ✅ decidido: CalVer como rótulo do que está no ar (§2) |
