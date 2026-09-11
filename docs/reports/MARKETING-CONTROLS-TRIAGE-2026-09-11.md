# Triagem de controles do Marketing — 2026-09-11

## Base e contagem verificadas

- Base funcional: `main` após o PR #597 (`d4c5086c15f68ee5102877c0bac47c03ff4c27f7`), empilhada sobre o commit transversal do PR #599 (`ccccaf4f5289b56419c5f300612dc253a5116cf7`).
- O commit transversal eliminou os 10 `<select>` nativos do código atual: todos usam `UiNativeSelect` do `operator-kit`.
- A varredura atual encontrou 40 call sites de `<input>`, 6 de `<textarea>` e 93 de `<button>`, excluídas as raízes dos próprios primitivos e um exemplo em comentário.
- O `tailwind.css` do Marketing importa `operator-theme.css`; o bloco `ESCALA DE DESIGN` tem o mesmo SHA-256 nos oito apps.

## Decisões do dono já registradas

Pablo aprovou na sessão transversal de Produção: campos com 44 px (`h-11`), fundo `bg-background` e foco `focus-visible:ring-[3px] focus-visible:ring-ring/50` acompanhado de `focus-visible:border-ring`. Essas escolhas deixam de ser gate nesta triagem e entram por primitivos compartilhados, sem novas receitas locais.

## Classificação antes da edição

### Acidental — migrar

- Inputs textuais, busca, senha, data e horário repetem receitas locais: usar `UiInput` quando a troca preservar tipo, atributos, evento e coerção.
- Os 6 textareas repetem receitas locais: usar `UiTextarea`.
- CTAs e ações outline comuns repetem dezenas de classes: usar `UiButton` e seus variants/sizes.
- H1 de tela fora da escala, rótulos comuns, números sem `tabular-nums`, `rounded-xl` estrutural e cores `amber` literais são desvios acidentais: alinhar à escala e aos tokens semânticos do app.

### Proposital — preservar e comentar no call site

- Checkboxes e radios nativos representam escolha binária/grupo e não são inputs textuais.
- Checkboxes `sr-only` sustentam chips de plataforma; botões com `aria-pressed` sustentam seletores segmentados, dias da semana e chips de público; botões com `role="tab"` sustentam abas.
- Ações exclusivamente de ícone migram para `UiIconButton` quando o contrato couber; o sino com badge permanece especializado. Os roots de `UiFilterChip`, `UiIconButton` e `UiSearchInput` são a implementação do próprio controle.
- Inputs numéricos com `v-model.number` permanecem nativos enquanto `UiInput` emitir apenas string; trocar hoje alteraria o contrato dos payloads.

Cada grupo preservado recebe um comentário de uma linha no call site explicando a exceção, para impedir uma futura “correção” mecânica.

## Resultado da triagem

- 10/10 selects usam `UiNativeSelect`; não resta `<select>` nativo no app.
- Os 6 textareas de negócio usam `UiTextarea`; o único `<textarea>` nativo restante é a raiz do próprio primitivo.
- Há 72 usos de `UiButton`, 16 de `UiInput` e 6 de `UiTextarea`. Os botões e inputs nativos restantes implementam os grupos propositais listados acima ou as raízes dos próprios primitivos.
- Os cinco H1 de página seguem `text-lg font-semibold`; rótulos de campo seguem `text-xs font-medium text-muted-foreground`; números dos tiles usam `tabular-nums`.
- A varredura não encontra `rounded-xl` nem cores literais `amber` nos SFCs do Marketing.
- O gate autenticado encontrou contraste de 3,33:1 no token compartilhado de aviso; a correção ficou com o dono do `operator-kit` no PR #599, que passou a proteger automaticamente tema claro/escuro, card/background e fundo sólido.

## Convivência e propriedade

- O PR #599 é dono dos componentes compartilhados, dos cinco arquivos Marketing sobrepostos e da extração de `OperatorLogin`; esta branch não reimplementa esse trabalho.
- A versão nova de `OperatorLogin` do PR #597 foi preservada como fonte no `operator-kit`, com sessão, foco e recuperação mantidos.
- Esta branch limita a mudança aos call sites e tokens restantes do Marketing e só será integrada depois do PR #599.

## Evidência de aceite

- Typecheck, lint e build de produção local: verdes.
- Vitest: 245/245 testes verdes.
- Fluxo E2E hermético: 1/1 verde; o operador entra e alcança Painel, Campanhas e Plataformas sem redigitação.
- Acessibilidade autenticada: 2/2 verdes, cobrindo teclado, axe, alvos de toque, reflow, movimento reduzido, tema escuro e cores forçadas.
- Matriz visual: 69/69 verde após revisão das 48 referências alteradas em mobile, desktop, tema escuro, erros, conflitos e estados degradados.
- A matriz detectou 26 px de overflow horizontal na paginação a 320 px; a composição móvel passou a duas linhas e foi medida em 320/320 px na lista e no formulário, mantendo a composição horizontal no desktop.
