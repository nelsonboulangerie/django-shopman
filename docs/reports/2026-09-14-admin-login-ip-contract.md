# Admin: fonte explícita do IP para rate limiting

Preparação do #655. Não liberar merge/deploy até validar o ingress do Admin. Nenhuma configuração real foi alterada por este patch.

`SHOPMAN_ADMIN_LOGIN_IP_SOURCE` é obrigatório: `direct` usa apenas REMOTE_ADDR e ignora headers; `do` usa apenas DO-Connecting-IP, depois de a operação provar a fronteira confiável. Valor ausente/desconhecido bloqueia `check --deploy` e responde 503 ao POST de login. GET permanece disponível. No modo DO, ausência, lista ou IP inválido também resulta em 503; não existe fallback XFF ou ajuste automático de profundidade. IPv6 é normalizado e IPv4-mapped IPv6 compartilha bucket com IPv4.

O seletor é uma declaração operacional, não autenticação de proxy: escolher `do` sem provar que toda rota acessível substitui headers fornecidos pelo cliente continua inseguro. O modo `direct` exige que REMOTE_ADDR realmente represente a conexão do cliente, não um LB.

## Evidência conhecida e prova faltante

- O spec versionado encaminha os hosts Admin e API diretamente ao componente web. Nitro encaminha outra conexão e tem topologia distinta; não copiar profundidade de BFF para Admin.
- A coordenação confirmou `DOORMAN_TRUSTED_PROXY_DEPTH=2` no ambiente. Isso não prova o caminho de cada host, a sobrescrita de header ou a inexistência de acesso alternativo.
- A [documentação oficial DO](https://docs.digitalocean.com/support/where-can-i-find-the-client-ip-address-of-a-request-connecting-to-my-app/) indica DO-Connecting-IP como endereço do cliente. A página não demonstra o resultado de enviar esse mesmo header forjado a todas as entradas deste deployment.
- Logs de SignInEvent exigem autenticação/tentativa e o helper atual lê XFF esquerdo; não serão usados como prova. `SHOPMAN_LOG_CLIENT_IP` imprime IP bruto e não será ativado. GET público comum não mostra o META recebido por Django.

Para liberar `do`, comprovar no staging equivalente: duas origens reais ficam separadas; uma origem permanece estável apesar de ingress rotativo; DO-Connecting-IP forjado é substituído, não preservado; XFF/CF-Connecting-IP/X-Real-IP não escolhem o bucket; todos os hosts e caminhos alternativos que alcançam `/admin/login/` satisfazem esse contrato ou estão efetivamente bloqueados. Mapear Admin, API, domínio padrão DO e eventual BFF. Teste sintético de RequestFactory prova o código, não a infraestrutura.

## Ensaio e remoção

Uma segunda mudança, separada e removível, prepara observação de GET normal no login, exclusivamente em staging, com token temporário e expiração. Nenhum endpoint echo, credencial de usuário ou conteúdo de header aparece na resposta. Logs contêm somente marcador sintético e HMAC temporário de endereços válidos; valores inválidos/listas recebem classificação genérica. A coordenação revisa essa mudança antes de qualquer deploy.

Após a prova, remover a instrumentação, seus testes e configurações temporárias; confirmar ausência de logs de probe; só então revisar a liberação do contrato permanente. Não incluir a instrumentação em produção. Uma evidência inconclusiva mantém #655 retido sem impedir os PRs independentes.
