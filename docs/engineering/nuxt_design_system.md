# Design compartilhado das superfícies Nuxt

- **Owner:** Design/Produto
- **Última verificação:** 2026-09-10 contra as superfícies do `HEAD`

Este documento registra somente padrões realmente compartilhados. O storefront é
branded; as oito superfícies de operador estendem `surfaces/operator-kit` e seguem o
canon de [`backstage-design-system.md`](backstage-design-system.md). Quando precisa de
uma família de controles, o app mantém primitivas vendadas em `app/components/Ui`,
construídas sobre Vue/Reka/Tailwind.
O repositório atual não depende de Nuxt UI; nomes `UButton`/`UCard` de documentos
antigos não são contrato do produto.

## Regra de composição

1. Reuse a primitiva `Ui*` existente na própria família de superfície.
2. Use props, variantes e slots antes de acrescentar classes locais.
3. Promova algo ao `operator-kit` somente quando dois consumidores reais provarem a
   mesma semântica. Necessidade exclusiva continua local.
4. Página coordena; componente apresenta; composable orquestra estado; função de
   `presentation/` transforma dados sem I/O.
5. Nenhuma camada visual deriva autorização, preço, estoque, consentimento, prazo ou
   transição. Renderize Projection + Actions do backend.

## Hierarquia e ergonomia

- Um título principal por página; títulos de seção não competem com ele.
- Corpo de texto em mobile nunca abaixo de 16 px; `text-xs` é reservado a badge ou
  metadado curto.
- Números comparáveis usam `tabular-nums`; cor nunca é o único portador de estado.
- Layout começa em uma coluna e acrescenta colunas sem remover informação.
- Todo alvo interativo mede ao menos 44×44 px ou possui área de toque equivalente
  testada. Ícone sem texto exige nome acessível.
- Modal tem nome, descrição, foco inicial, trap, fundo inerte, Escape quando seguro e
  restauração de foco. Código de X dígitos usa o componente de verificação, com grupo
  centralizado, colagem e anúncio acessível — nunca vários inputs artesanais soltos.
- A ação principal é inequívoca e ocupa a largura útil no mobile quando isso reduz
  erro. Ação perigosa não ganha destaque visual maior do que a opção segura recomendada.

## Omotenashi operacional

A interface deve reduzir trabalho real, não apenas parecer agradável:

- estado + consequência + próximo passo ficam no mesmo contexto;
- escolha segura aparece como recomendada, sem esconder alternativas legítimas;
- não pedir redigitação de dado já conhecido nem exigir memória entre telas;
- rascunho sobrevive a reload, navegação e expiração de sessão;
- conflito oferece comparação e reaproveitamento, nunca sobrescrita silenciosa;
- loading preserva contexto; vazio só aparece após fetch bem-sucedido; erro distingue
  login, proibição, conflito, validação, limite, indisponibilidade e offline;
- feedback persistente usa o próprio painel/comprovante; toast é apenas confirmação
  transitória;
- apresentação ao operador é pt-BR. Termo técnico em inglês só aparece quando é o
  identificador necessário para suporte ou auditoria.

Para fluxos de decisão, medir e registrar ao menos: decisões/toques, digitação,
mudanças de tela, espera, consultas externas, recuperação e certeza da consequência.
Guardas de segurança deliberadas podem exceder o budget, mas precisam de justificativa
explícita; não podem ser escondidas como fricção acidental.

## Estados e acessibilidade

- Loading: esqueleto da forma final ou mensagem específica; nunca vazio enganoso.
- Vazio: o que foi consultado, por que não há itens e uma única recuperação útil.
- Erro: causa em linguagem humana, request ID copiável quando útil e próximo passo.
- Resultado parcial/incerto: separar confirmado, aceito, falho, pendente e desconhecido.
- Teclado: ordem previsível, foco visível, sem armadilha fora de modal.
- WCAG 2.2 AA: axe sem `serious`/`critical`, 200% zoom, reflow a 320 px, contraste,
  forced colors, reduced motion e text spacing sem perda de conteúdo ou ação.
- Light/dark não mudam semântica; screenshots cobrem os dois quando suportados.

## Segurança de entrega

- Apps de operador são privados (`private, no-store`, `Vary: Cookie`) e não
  indexáveis.
- Assets compilados podem ser imutáveis; documentos, BFF, erros e SSE não.
- Fontes e assets de runtime são locais ou explicitamente aprovados.
- CSP, frame protection, HSTS em HTTPS, nosniff, referrer e permissions policy têm
  testes. Exceção de HMR existe somente em branch compile-time de desenvolvimento.
- Telemetria aceita allowlist e nunca conteúdo de anúncio, contato, membership,
  credencial ou segredo.

## Estrutura esperada

```text
app/
  components/       blocos reutilizáveis e primitivas Ui vendadas
  composables/      coordenação reativa e fronteiras HTTP
  pages/            rotas finas
  presentation/     transformação pura e copy pt-BR
  types/            tipos de consumo/apresentação
  assets/css/       tema canônico importado + exceções locais justificadas
server/
  api/              BFF same-origin
  routes/           SSE e health quando aplicáveis
```

## Gate antes de concluir

- unit/component cobrindo lógica e estados;
- lint, typecheck e build de produção;
- E2E do caminho principal e da recuperação crítica;
- axe + teclado + foco;
- matriz visual nos viewports/temas/estados relevantes;
- contratos de segurança e auditoria de dependências;
- instalação limpa e determinística.

No Marketing, essa cadeia é o job `Marketing — cadeia completa`: 320 px, mobile,
desktop, 200% zoom, light/dark, reduced motion, forced colors, conteúdo extremo,
confirmação, sessão expirada, conflito, parcial e `unknown`. O contrato factual e seus
budgets estão em
[`../reference/marketing-surface-contract.md`](../reference/marketing-surface-contract.md).
