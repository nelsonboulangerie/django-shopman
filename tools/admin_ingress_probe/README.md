# Imagem efêmera de observação

Este serviço não carrega Shopman, apps comerciais, banco, autenticação, sessões ou integrações. Usa Django/WSGI e o middleware observado para GET `/admin/login/`, com corpo fixo; `/health/` também é fixo. POST é recusado. O servidor single-process wsgiref é apenas para sete probes por host e origem em ambiente efêmero; não é servidor de produção ou teste de carga.

O build usa exatamente Dockerfile, .dockerignore, requirements.txt, server.py e observer_middleware.py, copiados por prepare_context.py. Nenhum checkout inteiro, .git, .env, chave, certificado ou configuração real entra no contexto. O token de teste é sintético e passado só no `docker run`, nunca no build. A verificação OCI confere hashes dos blobs, usuário não-root e ausência de variáveis de segredos na configuração da imagem. Isso prova a fronteira dos inputs deste build, não uma auditoria de toda a distribuição pública base.

A base Python 3.12 slim linux/amd64 foi resolvida na API pública Docker Registry em 14/09/2026 e fixada por digest. Esse digest é da **base**, não da imagem resultante. Dependências públicas seguem os pins Django/asgiref/sqlparse do repositório.

Workflow `.github/workflows/admin-ingress-probe.yml`: somente runner hospedado, contents:read, contexto mínimo, sem secrets/environments/registry/deploy. Um mesmo build exporta OCI e imagem Docker local ao runner. O container é testado sem rede externa e com filesystem read-only. verification.json registra separadamente OCI manifest digest, index digest e config digest; o config digest deve corresponder ao image ID efetivamente testado. O artifact dura um dia. Não alterar deploy-images ou o app online para usar esse artifact.

O teste local nativo e o teste em container Linux passaram. O run 34911644565 validou o manifest digest final `sha256:4f21922f646d1edc291b97947b06e456d163deee6c4c3cc3056165260e974c50`; veja o plano em docs/reports/2026-09-14-admin-ingress-ephemeral-plan.md para artifact e demais digests. O ambiente físico e as rotas reais ainda precisam da prova operacional do runbook, mesmo com imagem validada.
