# Triagem de controles de Pedidos — 2026-09-11

Classificação anterior à implementação dos pacotes visuais do brief. Não declara
encerrada a branch operacional, nem autoriza piloto, rollout ou efeitos externos.

## Proveniência e sequência

- Brief lido integralmente: arquivo externo
  `django-shopman-codex-briefs/CODEX-GESTOR-PEDIDOS-2026-09-10.md`, SHA-256
  `962f951b615a0a40e0371abee86023702b63cef0f9c97d9f315f09bd75393783`.
- Auditoria lida integralmente: `SURFACES-CONTROLS-AUDIT-2026-09-10.md`, SHA-256
  `fa0d4fbad0915767ae3f59fc2acbacf82ea40bf20a76c0da674f872c1795ac2a`.
  Suas contagens são da base `822aea24a`, não do código atual.
- Rebase dos 96 commits operacionais sobre `main` fixado em
  `0acb727ff8845595cff101ad23c77336681dcc9f`, incluindo PRs #599 e #601.
  Resultado inicial `aa412f87c14e62fb378a8a4443c933c6a084474b`.
  Histórico anterior preservado em `codex/orders-pre-brief-20260911` (`daf58b9c2`).
- Lidas as novas instruções de `CLAUDE.md`, o design system Nuxt e as triagens de
  Produção e Marketing. Não ativado o envelope de segurança opt-in em Pedidos.
- O brief exige **primeiro fechar a branch operacional**, depois PRs separados:
  **A** paletas/tokens; **B** campos; **C** botões. Esta triagem prepara essa fila;
  não mistura os três pacotes na branch operacional nem finge seu encerramento.

## Decisões do dono já comprovadas

O PR #599 registra em `PRODUCTION-CONTROLS-TRIAGE-2026-09-10.md` a escolha
transversal de Pablo: campos **44 px**, fundo **bg-background**, foco
**focus-visible:ring-[3px] focus-visible:ring-ring/50 + border-ring**.
O PR #601 reconhece expressamente essa aprovação como transversal. Portanto não
se reabre a pergunta h-9/h-11, fundo ou foco. O `UiNativeSelect` do kit já aplica
essa receita e os seis selects de Pedidos já o consomem.

## Classificação por achado

| Achado antigo | Revalidação / classe | Destino |
| --- | --- | --- |
| Selects de motivo sem altura | **Corrigido upstream**: OrderReasonDialog e index usam UiNativeSelect h-11 | Proteção de regressão nas jornadas de motivo; não recriar select |
| Inputs p-2.5 sem altura | **Parcialmente corrigido na branch operacional**: min-h-control já impõe 44 px; receitas de padding/foco ainda acidentais | B: usar UiInput quando tipo, eventos e coerção forem preservados |
| Textareas p-2.5 / areaClass | **Acidental**: receita duplicada; multiline exige altura mínima/rows, não altura fixa de input | B: UiTextarea, conservando rows, rótulos, draft, @input e atributos |
| fieldClass h-9 × UiInput h-11 | Altura antiga refutada: fieldClass agora min-h-control; **acidental** px-2.5/focus:ring-1 | B: receita aprovada; não reduzir alvo já protegido |
| text-amber-* como atenção | **Acidental**, permanece em cards, catálogo, detalhe, fila, alertas e painel de produto | A: text-warning; manter payload/tone e estado de negócio intactos |
| dark:text-orange-* sobre destructive | **Acidental**, permanece | A: text-destructive sem override; token dark já corrigido upstream |
| dark:text-lime-* sobre success | **Acidental**, permanece no courier e catálogo | A: text-success |
| text-white sobre destructive | **Corrigido upstream** nos call sites do brief | A: conferir regressão de contraste, sem substituição indiscriminada de branco |
| muted-foreground/30–60 | Separadores são decorativos; contagem, preço herdado, alça e acionadores carregam informação/interação | **Decisão do dono pendente** descrita abaixo; não alterar enquanto pendente |
| rounded-xl estrutural | **Acidental**: catálogo/feed/skeleton/erro diferem da regra escrita rounded-md | Ajuste próprio após sequência A/B/C; não misturar na migração de paleta |
| h2 uppercase/font-bold | **Acidental** nos títulos: design system §3 já define text-lg font-semibold para tela/seção | Ajuste próprio; labels/metadados não viram h2 por busca textual |
| Botões outline comuns | **Acidental**: ações de salvar/voltar/confirmar/rever/repetir usam receitas duplicadas | C: UiButton variant outline/default/destructive conforme semântica atual; preservar 48 px onde requerido |
| SearchInput/FilterChip/IconButton/Toolbar | Componentes existentes em Orders/Marketing; nenhuma terceira cópia necessária para este trabalho | Reusar existentes; extração transversal somente com contrato e consumidores comprovados |

## Famílias propositais a preservar

Cada família receberá comentário de **uma linha** no call site quando o pacote
dependente for executado; somente a barra invertida já o recebeu upstream.

| Família / call sites | Motivo e comentário preparado |
| --- | --- |
| catalog: select e ações da barra inferior invertida | `A barra invertida preserva contraste próprio e omite o chevron global.` Manter bg-none. |
| CatalogProductPanel: seletor de abas | `As abas compartilham borda de seleção e geometria do painel.` |
| index: board/table e opções de ordenação; catalog: operações de preço | `As opções compõem um único seletor, com estado de seleção explícito.` |
| OrderCard/index: seleção de pedidos | `O alvo seleciona a linha/cartão e conserva aria-pressed e geometria de seleção.` |
| catalog/feeds: switches | `O switch mantém estado binário e alvo de 44 px independente do trilho visual.` |
| catalog: menus de linha, acionador de preço e indicador de sincronização | `O controle pertence à célula e preserva alinhamento, contexto e alvo de toque.` |
| OrderReasonDialog: presets; detalhe: tags de nota | `O chip preenche o rascunho sem executar a ação final.` |
| AlertsBell: sino com contagem; botões de dispensar aviso | `O controle embutido mantém o aviso e sua ação no mesmo contexto.` Alvo insuficiente é defeito separado, não exceção ergonômica. |
| Inputs checkbox/radio/file e edição numérica com coerção nativa | `O input nativo preserva seleção, segurança do navegador ou coerção numérica do contrato.` |

Corpos de impressão, QR, Solari, branco físico, tamanho térmico, muted sobre muted
e equivalência border/border-border continuam fora desta correção, conforme os
achados refutados do brief. Não há novo componente Ui copiado.

## Decisão ainda necessária

**Hierarquia de opacidades:** recomendação apresentada a Pablo: token pleno para
informação e controles; opacidade apenas em separadores/ícones decorativos.
Vantagem: leitura e contraste mais estáveis; custo: menor diferenciação entre
metadados. Alternativa: manter hierarquia atual e corrigir apenas falhas medidas
de contraste; preserva aparência, mas exige validação de cada combinação/tema.
Sem resposta, ambos os ajustes de hierarquia permanecem pendentes. Isso não
suspende testes, rebase ou preparação dos pacotes independentes.

## Aceite e limites

A comparação de esforço dos pacotes visuais deverá manter o mesmo número de
ações, confirmações, permissões e digitação. Não se atribui ganho humano a uma
troca de classe. Antes/depois visual precisa cobrir light/dark, teclado, foco,
320 px, alvo 44/48 e os estados ocupado/desabilitado/conflito/unknown.
As jornadas integradas operacionais são regressão de comportamento; não
substituem observação em campo nem prova de contraste dos futuros pacotes.

O estado técnico, budgets não atendidos, migração/rollback e gates G01–G08 seguem
em `execution/orders-20260910/CURRENT-STATUS.md`. **T aberto; piloto preparado,
não iniciado; rollout não autorizado.**
