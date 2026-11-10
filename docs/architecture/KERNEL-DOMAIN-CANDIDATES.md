# Descoberta de novos domínios do Kernel

**Estado:** registro de descoberta, não autorização de implementação  
**Última revisão:** 2026-11-10  
**Dono das decisões de produto:** Pablo Valentini

Este documento preserva decisões e hipóteses sobre novos domínios sem promovê-las
prematuramente a ADR ou a item de implementação. Cada package novo ainda precisa passar
pela descoberta adversarial: pergunta canônica, autoridade própria, lifecycle, invariantes,
fronteiras, consumidores e prova de que um módulo de aplicação ou adapter não basta.

## Decisões confirmadas

### `Taskman`

O nome preferido é **Taskman**. O domínio pretendido é mais rico que uma lista de tarefas:

> Kernel de gestão operacional do trabalho: transforma compromissos pontuais, rotinas
> recorrentes e pequenos projetos em tarefas atribuíveis, verificáveis e auditáveis.

O primeiro caso de uso são as rotinas operacionais da loja. O conceito pode cobrir tarefas
avulsas, templates, recorrências, checklists, evidências, supervisão, apontamentos, ações
corretivas e projetos operacionais leves. Não nasce como gerenciador corporativo completo de
portfólio, orçamento, caminho crítico ou alocação financeira de projetos.

Há evidência concreta no proto-domínio existente em
`shopman/backstage/models/operation.py` e `shopman/backstage/services/operations.py`. Isso
fortalece a investigação, mas não substitui a revisão adversarial sobre extração, limites e
autoridade.

### `Spendman`

O nome preferido é **Spendman**, entendido como “o gastador”.

> Kernel candidato para registrar, comprovar, qualificar, aprovar e encaminhar gastos que
> nascem na operação.

Sua possível autoridade é a origem operacional comprovada do gasto: motivo, fornecedor,
valor, competência, evidência, autor, centro de custo operacional, aprovação, duplicidade e
estado de encaminhamento. Ele não deve possuir razão contábil, conciliação bancária, baixa
financeira ou pagamento.

O **Conta Azul** será a autoridade financeira e contábil externa. O Shopman deve oferecer uma
captura de despesas extremamente simples e enviar tudo ao Conta Azul por integração, sem
exigir que a operação use diretamente a interface do ERP. O contador continuará operando o
Conta Azul.

`Spendman` ainda é candidato a kernel. Se a necessidade real for apenas transformar um
formulário em uma chamada ao Conta Azul, a solução correta será um módulo de aplicação com
adapter. O package só se justifica com identidade local durável, lifecycle, evidência,
aprovação, deduplicação, auditoria e independência do provider financeiro.

### Capacidades futuras conhecidas

O ecossistema precisará, cedo ou tarde, tratar:

- Recursos Humanos e funcionários;
- assiduidade, integrada a um controle de ponto homologado;
- rotinas operacionais;
- equipamentos;
- projetos;
- captura e encaminhamento de gastos.

Essa lista é compromisso de evolução, não prova de que todos os itens sejam kernels separados.

## Nomes e fronteiras em avaliação

### `Human`

`Human` é o nome em avaliação para o domínio de pessoas e sua relação com a organização,
como exceção deliberada ao padrão `Somethingman`. A fronteira candidata inclui pessoa,
vínculo, função, lotação, competências, habilitações, treinamentos, afastamentos e fatos
consolidados de assiduidade.

O sistema de ponto homologado permanece autoridade legal das marcações. `Human` receberia
fatos normalizados por adapter e não inventaria nem corrigiria batidas. Folha de pagamento
também permanece fora.

O nome ainda não está confirmado. A descoberta deve testar se `Human` comunica uma fronteira
suficientemente precisa ou se é amplo demais.

### `Assetman` e `maintenance`

A separação candidata é:

- `Assetman`: identidade, localização, custódia, condição, garantia, medidores, falhas e
  histórico técnico dos ativos operacionais;
- `Taskman`: execução do trabalho preventivo ou corretivo;
- `Human`: pessoas e habilitações para executar o trabalho;
- `Craftsman`: centros de trabalho, capacidade produtiva e indisponibilidade;
- `maintenance`: módulo de aplicação e superfície que compõem essas autoridades.

O Odoo agrupa equipamentos, calendário, solicitações de manutenção e centros de trabalho em
seu produto Maintenance. Isso é uma boa experiência de produto, mas não prova que todos sejam
uma única autoridade no Kernel do Shopman.

O nome `Assetman` ainda não está confirmado. O teste decisivo é se equipamentos continuam
relevantes fora da manutenção. Custódia, garantia, calibração, disponibilidade e incidentes
indicam que provavelmente sim.

## Relações esperadas, sem dependência entre kernels

As relações devem ocorrer por refs, eventos e composição na camada de aplicação:

```text
Human ── quem pode/deve executar ──► Taskman
Assetman ── qual ativo requer ação ─► Taskman
Taskman ── trabalho concluído ──────► módulo maintenance ─► Assetman
Taskman ── gasto/evidência ─────────► Spendman ───────────► Conta Azul
```

Este diagrama descreve colaboração, não autoriza imports diretos entre packages.

## Próxima decisão

O primeiro caso real para o padrão de descoberta será provavelmente o `Taskman`. A análise
deve poder concluir por extração imediata, permanência temporária no Backstage ou rejeição do
package. “Já existe código” e “terá mais de um consumidor” são evidências, não critérios
suficientes. O critério é possuir pergunta canônica, linguagem, estado e invariantes próprios.
