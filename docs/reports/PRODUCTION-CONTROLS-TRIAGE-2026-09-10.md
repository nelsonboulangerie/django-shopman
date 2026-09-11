# Triagem de controles da Produção (2026-09-10)

Base final: `origin/main` em `d4c5086c1`, depois dos PRs #591–#597. Este relatório
registra a decisão antes do call site para que uma varredura futura não confunda
controle operacional deliberado com botão genérico duplicado.

## Resultado executado

- `<button>` cru em `production-nuxt/app`: **126 → 56**.
- `UiButton`: **9 → 79**. Os 70 casos migrados eram ações comuns: confirmar,
  cancelar, tentar novamente, salvar, publicar, atualizar, imprimir e abrir
  ações de CRUD.
- Cores de atenção/destruição passaram a tokens semânticos; não resta
  `text-amber-*`/`text-orange-*` na Produção.
- Raios avulsos `rounded-lg`/`rounded-xl`: **90 → 0** na Produção.
- Títulos apontados no brief usam `text-lg font-semibold`.

## Famílias propositais preservadas

| Receita | Onde | Por que não é `UiButton` |
|---|---|---|
| Segmentos compactos | `ProductionStageGrid`, `mise-en-place`, `expedite`, `reports`, `recipes/index`, `recipes/new` | As opções formam um único seletor mutuamente exclusivo; seleção e contorno pertencem ao conjunto. |
| Células e chips do quadro | `ProductionStageGrid` | Quantidade, sugestão e pedidos comprometidos precisam manter a geometria e o alinhamento da tabela. |
| Tiles de fornada + stepper | `ProductionStageGrid` | O tile identifica um registro com quantidade; `−/＋` têm alvo fixo de 48 px ao redor do número central. |
| Cartões de grau, motivo e perda | `QcCloseScreen` | Um cartão deliberadamente divide dois alvos: quantidade em cima e motivo embaixo; Perda repete o mesmo gesto. |
| Tiles de motivo de QC | `QcCloseScreen` | Cada escolha contém título e explicação e ocupa a célula inteira. |
| Cartão e teclado do forno | `expedite` | O cartão abre o timer, o tile lateral conclui a fornada e a matriz numérica mantém memória muscular. |
| Teclas Solari | `board` | Data, som, tela cheia e paginação pertencem à linguagem visual própria do kiosk. |
| Affordances embutidas | `ProductionHeader`, `RecipeHeader`, `IngredientPicker`, `mise-en-place` | Limpar campo, escolher opção de listbox e abrir detalhe vivem dentro de outra geometria; não são CTAs independentes. |
| Versão e edição de fórmula | `recipes/[ref]/index`, `recipes/[ref]/edit` | O tile de versão leva três linhas de metadados; ordenar/remover preserva a microbarra da linha; o disclosure ocupa toda a linha. |

Cada família tem agora um comentário de uma linha junto ao call site.

## Itens transversais concluídos

- `OperatorLogin` agora vive no `operator-kit`; as seis cópias e os formulários
  inline do Hub/PDV usam a mesma implementação. O PDV preserva, como variante
  explícita, campos de 48 px para o caixa touch.
- `OperatorSonner` centraliza o comportamento validado em Compras: topo,
  `rich-colors`, três avisos e tokens de sucesso/erro/atenção.
- O CSS de impressão de recibo foi removido do Hub.
- `text-destructive-foreground` substituiu branco fixo nos botões/badges
  destrutivos das superfícies de operador.
- `UiNativeSelect` agora vive no `operator-kit`: os **53 selects** de BI (8),
  Compras (8), Marketing (10), Pedidos (6), PDV (3) e Produção (18) usam o
  mesmo contrato, mantendo `bg-none` somente na barra invertida do catálogo.
- Campos comuns da Produção migraram para `UiInput`/`UiTextarea`. Inputs
  invisíveis de calendário, checkboxes, arquivo e steppers de 48 px continuam
  nativos porque a anatomia ou a segurança do navegador é diferente.

## Decisão do dono — aplicada em 2026-09-10

| Tema | Decisão | Razão |
|---|---|---|
| Altura de campo | **`h-11` (44 px)** para campos/selects; `h-9` somente para chips/inline. | Alvo de toque confortável no tablet. |
| Foco | **`focus-visible:ring-[3px] focus-visible:ring-ring/50` + `border-ring`**. | O dono preferiu explicitamente a alternativa mais intensa da comparação visual. |
| Fundo do campo | **`bg-background`**. | Mantém contraste estável dentro de cards e diálogos. |
| Atenção no tema claro | **`--warning: #9b5413`**, mantendo `--warning-foreground: #fff`. | Passa AA tanto como texto sobre `warning/10` + papel (4,66:1) quanto como fundo sólido com texto branco (5,72:1). |

As três escolhas foram aplicadas aos primitivos compartilhados, aos selects e
aos controles visíveis especializados da Produção. O PDV conserva a variante
de 48 px do login e os controles propositais mantêm sua geometria.
