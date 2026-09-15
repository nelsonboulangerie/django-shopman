# Destino efêmero para a prova de ingress — proposta, não provisionada

## Escolha mínima

Criar um app App Platform novo, com nome exclusivo `shopman-admin-ip-probe-<identificador>`, um serviço de 512 MiB (`apps-s-1vcpu-0.5gb`), uma instância e domínio padrão DO novo. Nenhum domínio da operação, DNS, banco, Redis, fila, armazenamento, integração ou segredo de produção. Usar região explicitamente conferida contra o app online na revisão central. Bloquear como destino o app ID `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f` e todos os seus hosts, inclusive o default ingress que contém “staging”.

A imagem mínima pode executar somente um observador HTTP/WSGI: GET `/health/` retorna 200 fixo; GET `/admin/login/` retorna página fixa e registra os mesmos fingerprints temporários de headers após token, host e prazo válidos; POST e demais caminhos retornam 405/404. Não precisa de Django completo para descobrir se o edge DO preserva ou substitui DO-Connecting-IP. Não usar servidor echo: dados da observação vão somente ao log restrito. A imagem precisa ser construída de fonte revisada, sem ENV/arquivos reais, testada localmente e referenciada por digest imutável no spec aprovado. Este plano não declara tal imagem já construída nem inventa digest.

Alternativa após a primeira prova: usar Django mínimo com a mesma versão do repositório e o middleware deste PR, settings isolados sem apps comerciais e view estática no mesmo caminho. Isso prova também a conversão WSGI→META e o middleware. Ainda não equivale a executar a aplicação inteira ou a entrar por um BFF.

## Sequência executável sob coordenação central

1. Aprovar esta opção e a imagem mínima; construir/testar/publicar somente essa imagem. Preparar um spec novo, sem copiar o spec vivo: nome único, região conferida, imagem por digest, serviço `observer`, porta 8080, uma instância de 512 MiB, health `/health/`, ingress `/`→observer, sem deploy automático, jobs ou bancos. Nenhuma criação paga é executada nesta tarefa.
2. Conferir o spec e executar centralmente `doctl apps create --spec <spec-efemero-aprovado>`. Registrar o ID retornado e estabelecer prazo operacional de exclusão de 60 minutos desde a criação; este prazo NÃO é um recurso automático da plataforma. Preparar a rotina central de limpeza antes da criação e remover o app mesmo se o build/deploy falhar.
3. Consultar o app pelo ID retornado, confirmar nome/serviço/region/default ingress, ausência de recursos reais e que o ID não é o app online. Só então preencher allowlist com o domínio efetivamente criado e configurar token novo e prazo de até 15 minutos. Se essa atualização exigir novo deploy, aguardar readiness e renovar a janela de forma explícita, sem deixá-la indefinida.
4. Rodar os cinco GETs do script em duas origens controladas: máquina local disponível remotamente e um runner GitHub hospedado, por exemplo. Não requer presença física. O runner recebe apenas token efêmero, ID e destino aprovados, nunca credenciais de usuário ou banco. A coordenação já terá conferido pela API DO a relação host→app ID. Se a máquina local estiver indisponível, usar outro executor já disponível; dois jobs/containers não provam sozinhos duas saídas IP.
5. Extrair logs do app efêmero pelo ID, correlacionar marcadores e preencher a matriz de igualdade, estabilidade e spoofing do runbook. Registrar se houve realmente duas origens distintas. Não interpretar ausência de logs como bloqueio ou sucesso.
6. Destruir o app efêmero pelo ID registrado, após confirmar novamente ID/nome e exclusão do app online. Consultar lista/apps para comprovar remoção, invalidar o token, eliminar fingerprints e artefatos de observação, preservar somente conclusão agregada. Remover a imagem temporária se não houver referência útil. Confirmar que não sobraram recursos criados fora do app.

## Custo e duração

Estimativa para uma instância, até uma hora: aproximadamente US$0,0074 de computação (`5 × 3600 / 2419200`), sujeita ao mínimo documentado de US$0,01, arredondamento e impostos. Reservar até US$0,05 para esta execução curta de um serviço; isso é orçamento de planejamento, não limite automático de cobrança. Se não for excluído, continua custando até US$5/mês. Não inclui eventuais minutos pagos do executor CI ou custos externos de registro/build; verificar a franquia antes de usar. Tráfego dos GETs é pequeno e não há necessidade de banco ou IP de saída dedicado. Preço e cobrança por segundo conferidos em 14/09/2026 na [documentação oficial](https://docs.digitalocean.com/products/app-platform/details/pricing/); a [regra de 28 dias](https://docs.digitalocean.com/platform/billing/bandwidth/) fundamenta o cálculo.

## O que esta prova NÃO libera

Um serviço mínimo em domínio padrão prova apenas a entrada DO desse app, região e imagem naquele momento. Não prova configuração Cloudflare de domínios personalizados, DNS/proxy da loja, authority routing do app online, acesso direto a componentes, passagem por Nitro, cookies, autenticação ou atomicidade Redis. Também não demonstra ausência de bypass de outra rota.

Para liberar `do` no #655 ainda é necessário comparar a topologia real e comprovar as entradas permitidas do Admin/API/backup/domínio padrão/BFF, ou apresentar regras verificadas que bloqueiem as alternativas. Se a configuração CF/custom domain for diferente, um ensaio representativo exige domínio isolado e configuração equivalente sob nova revisão central; não alterar DNS da operação para conseguir equivalência. Resultado positivo no app mínimo reduz incerteza, mas não será promovido a “produção comprovada”.


## Preparação concreta da imagem

`tools/admin_ingress_probe/` agora contém Dockerfile e serviço Django mínimo independente do Shopman. O contexto é uma allowlist de cinco arquivos e a base linux/amd64 está fixada por digest verificado na API Docker Registry. O teste HTTP/WSGI nativo passou. Como esta máquina não tem runtime de containers, o build e o teste Linux foram preparados em `.github/workflows/admin-ingress-probe.yml`, no executor GitHub já disponível, sem registry, secrets ou deploy. A imagem OCI, hashes do contexto e verificação do manifesto ficam em artifact com retenção de um dia. O digest da imagem final continua pendente até a execução concluir; não confundir com o digest da base nem com image ID/config digest.
