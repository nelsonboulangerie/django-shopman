# MKT-049 — CI completo e dependência Nuxt determinística

**Estado:** concluído na branch isolada  
**Runtime contratado:** Node 22.x  
**Nuxt instalado:** 4.5.2  
**Efeito externo:** nenhum

## Cadeia bloqueante

O `Surfaces Gate` ganhou o job **Marketing — cadeia completa**. Em um mesmo checkout,
ele instala `operator-kit` e Marketing com `npm ci` e executa unit/component, lint,
typecheck, build de produção, E2E, acessibilidade, regressão visual, contratos de
segurança e auditoria da árvore npm. Os resultados de navegador são preservados por
14 dias mesmo quando o job falha.

O job fixa `macos-15` e usa o Chromium da versão commitada do Playwright. Essa dupla
evita comparar pixels rasterizados por sistemas ou navegadores diferentes. E2E e
acessibilidade sobem seu próprio backend sem estado e o Nuxt em portas isoladas; não
dependem de banco, login, processo ou dado preparado por uma pessoa.

## Dependências e segurança

- `npm ci` em Node 22.23.1 instalou 869 pacotes sem alterar manifesto ou lock.
- O lock resolve `nuxt@4.5.2`, satisfazendo `^4.5.2`; não houve upgrade de Nuxt.
- `vitest` foi elevado somente de 4.1.10 para 4.1.11 para fechar
  GHSA-82fw-gwwq-j7x9.
- `js-yaml` foi fixado em 4.3.2 para fechar GHSA-2883-xcg3-v3hh.
- `npm audit --audit-level=high`: **0 vulnerabilidades**, contra 2 moderadas + 1
  alta encontradas antes da correção.

## Falhas reais encontradas pelo gate

1. O lint encontrou remoção dinâmica de chaves no merge de público. A implementação
   agora preserva o mesmo contrato por filtro imutável.
2. O ponto visual **Novo** em alertas aplicava `aria-label` a um `span` sem role. Ele
   agora é decorativo; o estado textual visível continua sendo a fonte acessível.
3. Em 320 px, o controle de edição de cada campanha encolhia a 9,7 px de largura. A
   linha passou a reorganizar a ação em mobile e todos os controles visíveis atendem
   ao budget de toque de 44 px. A lista caiu de 4.434 para 3.170 px de altura
   (**-28,5%**) sem reduzir de 12 para menos itens nem ocultar estado.
4. O teste visual ainda procurava o input único e a copy anteriores ao componente de
   código segmentado. O fluxo agora preenche as seis casas pelo nome acessível e aciona
   **Salvar configuração**.
5. Vinte e seis screenshots estavam anteriores às melhorias aprovadas depois do
   MKT-046. Foram comparados os estados críticos de mobile, confirmação, plataformas
   e detalhe; somente esses baselines foram regenerados. Os outros 43 permaneceram
   idênticos.

## Provas locais finais

- instalação: `npm ci` verde, `nuxt@4.5.2`;
- unit/component: **34 arquivos / 245 testes**;
- lint: verde;
- typecheck: verde;
- build SSR/Nitro de produção: verde;
- E2E hermético: **1 fluxo** de login → Painel → Campanhas/editor →
  Plataformas → Painel;
- acessibilidade: **2 fluxos** com axe WCAG 2 A/AA, teclado, modal/inert, reflow,
  tema, movimento reduzido, cores forçadas, overflow e alvos de toque;
- visual: **69/69 estados** contra screenshots pinados;
- segurança: **2 arquivos / 4 testes** e `npm audit` com zero vulnerabilidades;
- workflow YAML e `git diff --check`: verdes.

O job ainda não foi executado em GitHub porque nenhum push ou PR foi autorizado. A
mesma cadeia versionada foi executada integralmente no worktree. Nenhum provider,
credencial real, destinatário, rede de produção, deploy ou escrita externa foi usado.
