# WP-UX-8: Nuxt UI e Reka como infraestrutura canônica das superfícies de operador

**Status:** aprovado e lançado em 05/10/2026

**Plano pai:** [SUITE-UX-V2-PLAN](SUITE-UX-V2-PLAN.md)

**Escopo:** os oito apps Nuxt de operador

**Fora do escopo:** Storefront e Admin/Unfold

**Regra de entrega:** uma família de componentes ou um app por PR; nenhuma migração em massa sem prova visual e funcional

## 1. Mandato do dono

Revisar e aplicar Nuxt UI e Reka UI em **todas as telas** dos apps Nuxt de operador, com duas
intenções inseparáveis:

1. tornar estrutura, composição, semântica, estados, foco, teclado e acessibilidade canônicos;
2. preservar a identidade Shopman: cores, fontes, tokens, densidade, linguagem e adaptação ao
   contexto operacional.

Nuxt UI não entra como tema pronto. Ele é a referência de anatomia e, quando trouxer ganho
comprovado, também de solução visual. Reka UI é a fundação headless para os comportamentos
complexos. A decisão é feita componente a componente, e não por dogma de biblioteca.

O resultado precisa parecer um único produto Shopman, não uma coleção de demos do Nuxt UI e
nem oito implementações locais parecidas.

## 2. Perímetro

### 2.1 Apps incluídos

| Produto | Diretório | Vocação principal |
|---|---|---|
| Shopman Apps | `surfaces/hub-nuxt` | entrada e troca de app |
| PDV | `surfaces/pos-nuxt` | balcão e caixa |
| Cozinha | `surfaces/kds-nuxt` | estação e saída |
| Gestor | `surfaces/orders-nuxt` | pedidos, catálogo, clientes e canais |
| Produção | `surfaces/production-nuxt` | planejamento, chão e qualidade |
| Marketing | `surfaces/marketing-nuxt` | campanhas, ofertas e anúncios |
| Compras | `surfaces/purchase-nuxt` | fornecedores, compra e recebimento |
| B.I. | `surfaces/bi-nuxt` | análise e decisão |

### 2.2 Exclusões deliberadas

- `surfaces/storefront-nuxt`: superfície de cliente, com marca, voz e necessidades próprias.
- Admin/Unfold: segue sua infraestrutura canônica própria.
- Mudanças de regra de negócio, contrato de API, permissão ou lifecycle sem necessidade direta
  para preservar uma interação existente.
- Redesenho visual gratuito. Toda mudança de aparência precisa resolver um problema nomeado.
- Troca de URL ou arquitetura de navegação. Esse trabalho pertence ao WP-UX-12, embora os
  componentes compartilhados usados por ele sejam entregues aqui.

## 3. Estado encontrado no lançamento

Levantamento mecânico em `origin/main` no dia 05/10/2026:

| evidência | quantidade |
|---|---:|
| arquivos de rota em `app/pages` | 59 |
| shell adicional da Central, concentrado em `app.vue` | 1 |
| componentes Vue locais nos oito apps | 424 |
| arquivos nas árvores locais `components/Ui` | 270 |
| arquivos que referenciam Reka nos apps | 262 |
| ocorrências preliminares de `button`, `select` ou `textarea` nativos | 221 |

As ocorrências nativas não são automaticamente defeitos. Um elemento HTML simples pode ser a
escolha correta. Elas são pontos de auditoria para conferir estados, foco, tamanho de alvo,
atalhos e consistência.

As maiores duplicações locais são:

- seis cópias de Button, Input, Card e da família Sheet;
- cinco cópias das famílias Dialog, Popover, Tooltip, Alert, Textarea, Badge e Separator;
- overlays e controles segmentados adicionais implementados diretamente nas telas;
- o `operator-kit`, que deveria ser o dono da infraestrutura, ainda contém menos primitivas
  que os apps consumidores.

O problema não é só volume duplicado. Componentes de overlay copiados podem divergir em
focus trap, scroll lock, fechamento por Escape, portal, ordem das camadas e leitura por
tecnologia assistiva. A migração trata comportamento antes de tratar estética.

## 4. Decisões de arquitetura

### 4.1 Um único ponto de consumo

As telas importam componentes canônicos do `operator-kit`. Elas não importam `@nuxt/ui` ou
`reka-ui` diretamente depois de migradas, salvo exceção curta, documentada e testada.

```text
tela do app
    ↓
componente Shopman do operator-kit
    ↓
Nuxt UI, Reka UI ou HTML semântico
```

Isso mantém uma API própria e permite trocar a implementação sem reescrever oito produtos.
Nomes e props não devem vazar detalhes acidentais da biblioteca para as telas.

### 4.2 Duas decisões independentes por componente

Cada família recebe dois vereditos separados:

| eixo | opções válidas |
|---|---|
| **estrutura e comportamento** | componente Nuxt UI; primitivo Reka; HTML semântico |
| **aparência** | Shopman atual refinado; anatomia Nuxt UI adaptada; aparência Nuxt UI adaptada |

É válido adotar a estrutura do Nuxt UI e manter toda a aparência Shopman. Também é válido
adotar parte da aparência do Nuxt UI quando ela melhorar hierarquia, legibilidade, estados,
densidade ou adaptação ao dispositivo. Nenhuma aparência entra apenas por ser o default da
biblioteca.

### 4.3 Nuxt UI direto como regra; Reka direto como exceção provada

O WP começa pelo componente Nuxt UI consumido por um wrapper Shopman fino, com tema,
idioma e slots próprios. A composição publicada na documentação oficial é a baseline:
não se reproduz visualmente um componente com botões, campos ou estados paralelos.

O Nuxt UI direto é preferido quando:

- reduz código e estados locais de forma material;
- SSR, hidratação, Teleport, CSP e árvore de foco permanecem corretos;
- o custo de bundle fica dentro do orçamento do §10;
- a personalização não exige lutar contra classes e defaults;
- a API Shopman permanece estável e pequena.

Reka direto só é aceito quando:

- a interação operacional exige anatomia própria;
- o componente Nuxt UI acrescenta camadas ou peso sem benefício;
- o comportamento precisa ser especializado para estação, scanner, teclado ou toque;
- a aparência só seria obtida anulando a maior parte do componente pronto;
- a divergência de anatomia, o ganho operacional e os testes de não regressão ficam
  registrados no ledger da família.

HTML semântico continua sendo a escolha certa para controles simples sem estado composto.

O Nuxt UI oferece modo sem tema e customização por slots. Eles devem ser avaliados na prova,
não assumidos como resposta automática. Referências oficiais:

- [Nuxt UI](https://ui.nuxt.com/docs/getting-started)
- [Tema do Nuxt UI](https://ui.nuxt.com/theme)
- [Reka UI](https://reka-ui.com/)

### 4.4 Identidade visual permanece Shopman

São invariantes:

- Instrument Sans e a escala tipográfica `op-*`;
- tokens semânticos do `operator-theme.css`;
- neutro como base e cor somente com significado;
- contraste, foco, densidade e tamanho de alvo próprios de cada contexto;
- vocabulário e copy canônicos em português;
- ícones Lucide empacotados pela infraestrutura atual;
- modos claro e escuro conforme a vocação de cada app;
- ausência de classes cruas de paleta fora da camada de tokens.

### 4.5 Especialização por dispositivo é parte do componente

Responsividade não termina em breakpoint. Cada componente precisa declarar como serve:

| contexto | exigência mínima |
|---|---|
| desktop com teclado | ordem de foco estável, atalhos visíveis, estados de hover e foco, densidade eficiente |
| tablet com toque e giro | alvos adequados, painéis e overlays compatíveis com orientação, ausência de hover obrigatório |
| celular | operação com polegar, áreas seguras, teclado virtual, câmera e ações fixas sem cobrir conteúdo |
| estação/kiosk | foco e Escape previsíveis, tela cheia recuperável, scroll lock e camadas robustas |

Componentes que não têm uso legítimo em um perfil podem declarar a exclusão. A exclusão precisa
ser intencional e testada, não consequência de layout quebrado.

## 5. Matriz de decisão por família

O veredito inicial orienta a investigação. A prova da Fase 0 pode refiná-lo.

| família | referência Nuxt UI | fundação provável | aparência inicial | risco principal |
|---|---|---|---|---|
| Button e IconButton | Button | HTML semântico | Shopman | estados, loading e alvo de toque |
| Input, Textarea e Field | Input, Textarea, FormField | HTML semântico | Shopman com anatomia refinada | label, erro e descrição desconectados |
| Checkbox, Radio e Switch | Checkbox, RadioGroup, Switch | Reka | Shopman | teclado e estado indeterminado |
| Select e Combobox | Select, SelectMenu, InputMenu | Reka/Nuxt UI | avaliar caso a caso | busca, portal, teclado virtual |
| Dialog e confirmação | Modal, AlertDialog | Reka/Nuxt UI | Shopman | foco, empilhamento e ação destrutiva |
| Sheet, Drawer e Slideover | Slideover, Drawer | Reka/Nuxt UI | anatomia adaptativa | gesto, área segura e scroll |
| Popover, Menu e Tooltip | Popover, DropdownMenu, Tooltip | Reka/Nuxt UI | Nuxt UI adaptado é candidato | camadas e navegação por setas |
| Tabs e SegmentedControl | Tabs | Reka | Shopman | roving focus e overflow móvel |
| Stepper | Stepper | Reka | clássico Shopman | linearidade e descrição móvel |
| CommandPalette e busca | CommandPalette | Nuxt UI/Reka | anatomia Nuxt UI adaptada | busca assíncrona e alcance |
| Toast e feedback | Toast | Nuxt UI ou infraestrutura atual | Shopman | duplicação e anúncio por leitor |
| Alert e Empty | Alert, Empty | Nuxt UI ou HTML semântico | Shopman | consistência de estado |
| Skeleton | Skeleton | Nuxt UI | Shopman | forma final, anúncio acessível e movimento reduzido |
| Card e Stat | Card | HTML semântico | Shopman | hierarquia e ações concorrentes |
| Table e DataTable | Table | Nuxt UI ou tabela semântica | caso a caso | mobile, seleção e virtualização |
| Pagination | Pagination | Nuxt UI/Reka | Shopman | nome acessível e alvo |
| Accordion e Collapsible | Accordion, Collapsible | Reka | caso a caso | foco e conteúdo oculto |
| Navigation e Sidebar | NavigationMenu, Sidebar | Nuxt UI/Reka | anatomia Shopman v3 | rotas, mobile e estação |
| Data, período e hora | InputDate, Calendar, InputTime, FormField | Nuxt UI | adaptada ao domínio | fuso, limites, teclado e toque |
| Painéis redimensionáveis | Splitter | Nuxt UI/Reka | Shopman | persistência, teclado e colapso móvel |
| FileUpload e captura | FileUpload | HTML/Nuxt UI | especializada | câmera, tamanho e permissão |

O stepper de Campanhas, validado no PR #1485, é o primeiro exemplo: Reka fornece a estrutura e
os estados; a aparência, a copy, a navegação não linear e o comportamento móvel permanecem
Shopman.

## 6. O ledger que prova “todas as telas”

A Fase 0 cria `docs/reference/operator-component-ledger.json`, validado por teste. Cada tela ou
subtela operacional recebe uma entrada. Não basta enumerar arquivos de rota, porque Compras e
outras superfícies concentram várias telas em um único arquivo.

Cada entrada contém:

```json
{
  "app": "marketing",
  "surface": "campaign-form",
  "routes": ["/campaigns?new=1", "/campaigns?edit=<ref>"],
  "profiles": ["desktop-keyboard", "tablet-touch", "mobile-touch"],
  "families": ["field", "select", "stepper", "dialog", "button"],
  "functionalInventory": "tests/inventory/campaign-form.inventory.ts",
  "status": "migrated",
  "exceptions": []
}
```

Estados possíveis: `pending`, `audited`, `migrated`, `retained-with-reason`. O CI reprova:

- rota ou subtela conhecida sem entrada;
- família usada sem veredito;
- `retained-with-reason` sem justificativa, responsável e teste;
- entrada marcada como migrada que ainda importa implementação local proibida.

## 7. Fases e PRs

### Fase 0: prova técnica, ledger e baseline

Entregas:

1. inventário completo de telas, subfluxos e famílias usadas;
2. prova Nuxt UI direto versus Reka direto no `operator-kit`;
3. medição de bundle, SSR, hidratação, foco, camadas e CSP;
4. API canônica inicial e convenção de nomes;
5. guardrail em modo relatório, ainda sem bloquear a suíte;
6. matriz visual desktop, tablet e celular dos componentes-piloto.

Gate: o PR registra qual estratégia venceu por família. Nenhuma migração em massa começa antes
desse veredito.

### Fase 1: fundação do `operator-kit`

Entregas:

- Button, IconButton, Input, Textarea, Field, Card, Badge, Alert, Separator, Skeleton e Empty;
- tokens de variante, tamanho e estado;
- contratos únicos de `disabled`, `loading`, erro, descrição e ícone;
- documentação viva com exemplos Shopman, não a demo visual do fornecedor.

Mudança visual: nenhuma por padrão. Ajustes ficam limitados a defeitos de hierarquia, alvo,
contraste ou estado encontrados e documentados.

### Fase 2: camadas e foco

Entregas:

- Dialog, AlertDialog, Sheet/Drawer/Slideover, Popover, DropdownMenu e Tooltip;
- uma única pilha de overlays;
- focus trap, retorno de foco, Escape, portal, scroll lock e áreas seguras;
- confirmação destrutiva única, sem atalhos que a contornem.

Gate: testes de diálogo sobre diálogo, menu dentro de sheet, teclado, toque, zoom e leitor de
tela. Essa fase elimina os overlays manuais catalogados.

### Fase 3: seleção, formulário e sequência

Entregas:

- Checkbox, RadioGroup, Switch, Select, SelectMenu/Combobox e InputMenu;
- Tabs, SegmentedControl e Stepper;
- Calendar/DatePicker e controles numéricos onde já houver uso;
- associação canônica entre campo, label, ajuda, erro e validação assíncrona.

Gate: teclado completo, IME, teclado virtual, rotação e retomada de rascunho.

### Fase 4: dados, feedback, busca e navegação

Entregas:

- Table/DataTable, Pagination, Accordion/Collapsible e estados de lista;
- CommandPalette e peças necessárias à busca única do WP-UX-2;
- NavigationMenu e Sidebar necessários à anatomia do WP-UX-12;
- feedback único para toast, alertas, carregamento, vazio e erro.

Gate: tabelas e listas permanecem úteis no celular; transformar tabela em card é permitido
quando a tarefa muda com o dispositivo, desde que nenhum dado ou ação desapareça.

### Fase 5: migração por produto

Cada app recebe um PR próprio, ou mais de um quando ultrapassar aproximadamente 800 linhas de
mudança. Ordem:

1. **Gestor**, piloto e referência de escritório;
2. **Marketing** e **B.I.**, validando formulários, tabelas, gráficos e decisão móvel;
3. **Compras**, validando câmera, recebimento e toque em campo;
4. **Shopman Apps**, validando shell e navegação da suíte;
5. **Produção** e **Cozinha**, validando estação, kiosk, giro e operação sob pressão;
6. **PDV**, por último, depois que teclado, scanner, foco e overlays estiverem provados.

Cada PR começa pelo inventário funcional da tela e termina com o de-para “função anterior →
novo lugar” por perfil de dispositivo.

### Fase 6: remoção e trava definitiva

Entregas:

- apagar árvores `components/Ui` substituídas;
- remover imports diretos de Reka e Nuxt UI dos apps;
- remover CSS e testes mortos;
- ligar os guardrails em modo bloqueante;
- publicar o placar final do ledger, sem entradas `pending`.

## 8. Regras para adoção visual do Nuxt UI

Uma proposta visual só entra se responder “sim” a pelo menos uma pergunta:

1. melhora a hierarquia da decisão principal?
2. torna estado, seleção, erro ou risco mais legível?
3. reduz espaço sem reduzir compreensão ou alvo de toque?
4. melhora desktop, tablet ou celular em seu contexto real?
5. elimina um padrão local inconsistente que o operador precisaria reaprender?

E precisa responder “não” a todas estas:

- introduz aparência genérica ou desalinhada aos tokens Shopman?
- usa cor decorativa ou cria outro significado para cor existente?
- esconde função, filtro, estado, atalho ou informação atual?
- reduz alvo de toque, legibilidade ou previsibilidade por teclado?
- exige exceções repetidas só para vencer defaults da biblioteca?

O PR registra o veredito visual como `manter`, `refinar` ou `adotar adaptado`, com captura antes
e depois. “É o default do Nuxt UI” não é justificativa.

## 9. Trava de não regressão

Toda migração precisa provar:

1. **Paridade funcional:** todas as ações, filtros, opções, informações, permissões, estados,
   atalhos e recuperações do inventário anterior continuam alcançáveis.
2. **Semântica:** papéis, nomes acessíveis, relações de label e anúncios de estado são testados.
3. **Teclado:** Tab, Shift+Tab, Enter, Espaço, Escape e setas funcionam conforme o componente;
   atalhos do app não disparam dentro de campo ou overlay.
4. **Toque:** alvos e gestos funcionam sem hover e sem colisão com áreas seguras.
5. **Foco:** abertura, fechamento, erro e avanço levam o foco ao lugar correto e o devolvem.
6. **Camadas:** menus, popovers, sheets, diálogos e toasts não disputam portal ou z-index.
7. **Visual:** light/dark quando suportado; desktop, tablet retrato/paisagem e celular.
8. **Dados:** nenhum contrato com backend muda silenciosamente.
9. **Performance:** orçamento do §10 respeitado.
10. **Copy:** vocabulário canônico, sem inglês residual e sem travessão visível.

## 10. Orçamento técnico

A Fase 0 mede o baseline real e grava os números. Até lá, valem estes limites relativos:

- nenhuma segunda cópia de Reka no bundle;
- crescimento de JavaScript inicial por app inferior a 5%, salvo aprovação com medição de uso;
- componente não usado não entra no chunk inicial;
- nenhuma regressão estatisticamente relevante de LCP, INP ou hidratação nas matrizes existentes;
- nenhuma chamada externa para ícone, fonte, estilo ou runtime;
- build SSR e navegação hidratada sem warnings novos.

Se o Nuxt UI direto exceder esses limites, a família usa Reka ou HTML por trás do wrapper
Shopman. A biblioteca não ganha prioridade sobre a experiência.

## 11. Guardrails de CI

O WP entrega verificações mecânicas para:

- impedir nova árvore `components/Ui` em app de operador;
- impedir import direto de `@nuxt/ui` ou `reka-ui` fora do `operator-kit`, com allowlist curta;
- garantir uma única versão travada das dependências compartilhadas;
- detectar overlay manual novo (`fixed inset-0`, role dialog e handlers equivalentes) fora das
  abstrações autorizadas;
- exigir entrada no ledger para toda tela/subtela;
- impedir classes de paleta proibidas em componentes canônicos;
- executar testes de contrato dos wrappers em todos os apps consumidores.

Os guardrails entram primeiro em modo relatório e tornam-se bloqueantes por família migrada.
Assim, o projeto não fica congelado durante a transição e também não volta a divergir.

## 12. Critérios de aceite do WP

O WP só termina quando:

- [ ] todas as telas e subtelas dos oito apps constam do ledger;
- [ ] todas as famílias usadas têm veredito estrutural e visual registrado;
- [ ] os apps consomem os wrappers canônicos do `operator-kit`;
- [ ] não restam árvores `components/Ui` duplicadas;
- [ ] não restam imports diretos não justificados de Nuxt UI ou Reka nos apps;
- [ ] não restam overlays manuais inventariados;
- [ ] cada tela passou pela matriz desktop, tablet e celular aplicável;
- [ ] inventários funcionais e testes anteriores continuam verdes;
- [ ] testes de componente, a11y, visual, SSR, build, lint e typecheck estão verdes;
- [ ] o orçamento de bundle e performance foi respeitado;
- [ ] o relatório final lista toda exceção retida e seu motivo operacional;
- [ ] os guardrails impedem que a duplicação reapareça.

## 13. Relatório obrigatório por PR

Cada entrega deste WP inclui:

| item | conteúdo |
|---|---|
| família ou telas | escopo exato |
| decisão estrutural | Nuxt UI, Reka ou HTML, com motivo |
| decisão visual | manter, refinar ou adotar adaptado |
| paridade | função anterior e novo lugar |
| dispositivos | desktop, tablet e celular aplicáveis |
| acessibilidade | teclado, foco, semântica e leitor |
| evidência visual | antes/depois nas matrizes existentes |
| performance | delta de bundle e métricas relevantes |
| testes | comandos e resultados, não apenas contagem |
| exceções | dívida retida, responsável e follow-up |

## 14. Dependências e convivência com os outros WPs

- Este documento é a especificação executável do **WP-UX-8** do plano pai.
- WP-UX-12 consome navegação, guardas e overlays daqui.
- WP-UX-6 consome Field, Empty, Skeleton e Alert daqui.
- WP-UX-2 consome busca, menu, segmentado e barra de ações daqui.
- WP-UX-10 consome popover, menu, tooltip e feedback daqui.
- WP-UX-13 usa os mesmos wrappers, mas decide quando a tarefa muda por dispositivo.
- WP-UX-9 migra as telas ricas depois que os contratos deste WP estiverem estáveis.

Quando outro WP precisar de uma família ainda não migrada, ele pode antecipá-la seguindo este
contrato e entregando-a no `operator-kit`; não pode criar mais uma cópia local.

## 15. Primeiro incremento executável

O primeiro PR de implementação após este lançamento deve conter apenas:

1. ledger completo dos oito apps;
2. prova técnica com uma família simples e uma composta;
3. medição de bundle, SSR, foco e camada;
4. decisão registrada sobre Nuxt UI direto versus Reka direto;
5. guardrail em modo relatório;
6. nenhuma migração visual ampla.

Famílias sugeridas para a prova:

- **Button/Field**, para validar tokens, variantes, auto-import e tree-shaking;
- **Dialog/Popover**, para validar Reka único, Teleport, empilhamento e foco.

Só depois desse gate começa a remoção das cópias locais.
