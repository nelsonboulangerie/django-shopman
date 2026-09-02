# WP-IDENT-PT-BR — Identificador em português nas superfícies

> **Estado:** proposto (02/09/2026), pré-go-live. Não iniciado.
> **Origem:** a pergunta do dono ao ver `chaveDoGesto` citado num relatório —
> *"existe assim no código, em pt-br?"*. Existe, e não está sozinho.

## A regra que está sendo violada

`CLAUDE.md`: **identificador em inglês**, com três exceções que são regra e não
julgamento — `cpf`/`cnpj`/`cep` (nome próprio de documento brasileiro), **prosa**
(docstring, comentário, cópia de tela) e **campo de API de terceiro** (o `valor`
da Efí sobrevive porque é o contrato deles, e morre na porta de entrada).

`chaveDoGesto` não é nenhuma das três.

## O tamanho real: 36 declarações em 20 arquivos

⚠️ **O grep cru mente por um fator de ~10, e a primeira medição desta auditoria
caiu nisso.** Contar `\bresposta\b` devolve 94 ocorrências em 58 arquivos —
quase tudo **comentário e string**, que a regra da casa manda deixar em
português. Medir identificador exige remover comentários e literais primeiro e
contar só DECLARAÇÕES.

Medido em 02/09, dessa forma:

| superfície | declarações | arquivos |
|---|---|---|
| `pos-nuxt` | 20 | 8 |
| `marketing-nuxt` | 6 | 3 |
| `storefront-nuxt` | 5 | 5 |
| `operator-kit` | **3** | 2 |
| `orders-nuxt` | 2 | 2 |
| **total** | **36** | **20** |

Os nomes: `duracao` (4), `resposta` (3), `corpo` (3), `linhas` (3),
`resultado` (3), `ultimaTentativa` (2), `primeira` (2), `prefereMenosMovimento`
(2), `ehRotaDeAutenticacao` (2), e mais doze com uma ocorrência cada — entre eles
`chaveDoGesto`, `novaChave`, `comChave`, `cancelarComAprovacao`, `assinatura`,
`abrirTela`, `semCliente`/`comCliente`, `semNome`, `secao`, `chamada`.

**As 3 do `operator-kit` são as mais caras**, e não por quantidade: o layer é
importado por sete apps, então um nome em pt-br ali é a convenção quebrada
*herdada* por todo mundo. Começar por elas.

## Por que não fazer agora, e o que muda depois

Rename em massa é **hostil a merge** (regra registrada da casa). Com 9 PRs
abertos e ~45 worktrees sujas, mexer em 20 arquivos hoje gera conflito em
frentes que não têm nada a ver com isto — e às vésperas do go-live o custo do
conflito é maior que o do nome errado.

**Gatilho de execução:** fila de merge vazia. Não "quando der".

## Procedimento seguro

1. **Um PR por superfície**, na ordem `operator-kit` → `orders-nuxt` →
   `storefront-nuxt` → `marketing-nuxt` → `pos-nuxt` (o maior por último, e é a
   tela do dinheiro).
2. **Renomear só a declaração e seus usos** — nunca comentário, string ou cópia
   de tela. A prosa continua em português; é regra, não descuido.
3. **O gate é o `nuxi typecheck`**, não o grep: identificador renomeado pela
   metade não compila. Rodar a suíte da superfície + typecheck **antes** de abrir
   o PR.
4. **Zero resíduos** (regra pré-go-live): o nome antigo não sobrevive nem em
   comentário. Depois do `git tag go-live-v1`, vale o ADR-015 e a regra muda.
5. `chaveDoGesto` → `gestureKey`, `novaChave` → `newKey`, `comChave` →
   `withKey`, `ultimaTentativa` → `lastAttempt`. O comentário que explica a
   regra dos dois casos (mesma chave no retry, chave nova no sucesso) **fica em
   português** — é prosa, e é o que ensina.

## Como remedir

Este é o script da medição acima; ele exclui comentários e literais e conta só
declarações. Rodar antes e depois de cada PR:

```python
import re, pathlib, collections
S = pathlib.Path("surfaces")
PT = {"resposta","resultado","linhas","corpo","assinatura","movimento","opcoes","secao",
      "chamada","chaveDoGesto","novaChave","comChave","ultimaTentativa","abrirTela",
      "cancelarComAprovacao","ehRotaDeAutenticacao","prefereMenosMovimento","aprovacao",
      "denominacoes","tentativa","primeira","terceira","duracao","capacidade","comCliente",
      "semCliente","comInsumo","semInsumo","semNome","semQuantidade"}
DECL = re.compile(r"\b(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)")
def strip_noise(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S); t = re.sub(r"//[^\n]*", "", t)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    for q in ('"', "'", "`"):
        t = re.sub(rf"{q}(?:[^{q}\\]|\\.)*{q}", q*2, t)
    return t
c = collections.Counter()
for f in S.rglob("*"):
    if f.suffix not in (".ts", ".vue") or "node_modules" in f.parts: continue
    for n in DECL.findall(strip_noise(f.read_text(encoding="utf-8"))):
        if n in PT: c[n] += 1
print(sum(c.values()), "declarações"); print(c.most_common())
```

⚠️ `PT` é uma **allowlist**, não um detector. Ela pega o que já se sabe existir.
Um nome novo em pt-br não aparece aqui — a defesa contra isso é a revisão, e a
heurística morfológica (`-cao`, `-mento`, `-avel`, `-eiro`) para varrer de novo
periodicamente. Cognatos (`total`, `data`, `fiscal`) e a exceção documentada do
`MovementType` do caixa (`sangria`/`suprimento`) ficam **fora** de propósito.

## Fora de escopo

- **`MovementType` do caixa** (`SANGRIA`/`SUPRIMENTO`/`AJUSTE`): já é pendência
  nomeada em `CLAUDE.md`, com valor gravado no banco e impresso no comprovante.
  É WP próprio, com migração.
- **Python.** Esta medição cobriu `surfaces/`. O backend não foi medido, e a
  suspeita é que esteja mais limpo (a convenção nasceu lá) — mas *suspeita não é
  medição*, e isso deve ser dito em vez de assumido.
