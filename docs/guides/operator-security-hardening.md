# Hardening de acesso do operador (pré-produção)

> Endurecimento de acesso às superfícies de operador (Admin Django + apps Nuxt
> de operador) antes do go-live. Cobre 2FA do admin e restrição por IP no
> ingress. Faz parte do Lote C do
> [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md).

---

## 1. 2FA (TOTP) no Admin

O Admin oferece adesão individual com `django_otp`, `otp_totp` e recuperação `otp_static`. O [roteiro completo do piloto](../reports/2026-09-15-admin-2fa-pilot.md) descreve inscrição, limites e recuperação.

1. Após publicação coordenada e migrações, a operação prepara `python manage.py setup_admin_totp <username>` em console privado. O comando não imprime segredo e não confirma o fator.
2. O titular entra em `/admin/2fa/enroll/`, confirma a senha, escaneia o QR, valida o TOTP, guarda a lista de recuperação e consome um código para concluir. Não enviar códigos ou QR para logs, chat ou CI.
3. Somente essa conclusão ativa a exigência individual no Admin. O marcador durável permanece mesmo se acabarem ou forem apagados os códigos/dispositivos. Outros staff e o PDV não aderem automaticamente.
4. Manter `SHOPMAN_ADMIN_REQUIRE_2FA` OFF durante o piloto. Um rollout global futuro exige inscrição e recuperação confirmadas de todos os staff ativos, `check_admin_2fa_ready` verde e decisão coordenada de configuração.

Para substituir um autenticador perdido, entrar usando senha e um código de recuperação guardado. A operação prepara `setup_admin_totp <username> --force`; o titular confirma o substituto na sessão verificada. Os fatores antigos só são revogados ao concluir autenticador e recuperação novos.

Perder todos os fatores/códigos exige recuperação operacional supervisionada e identidade verificada; não existe reset remoto baseado só em senha. **Desligar a flag global não desativa uma adesão individual.** Não apagar o marcador nem reverter sua migração para contornar o gate.

---

## 2. IP allowlist no ingress (não no app)

**Decisão (2026-06-26): restrição por IP é responsabilidade do _ingress_, não de
um middleware app-level.** Fecha o TODO de
[`config/settings.py`](../../config/settings.py) (`# combinar com IP allowlist no
ingress do admin`).

### Por quê ingress e não middleware

Um middleware Django teria que confiar em `X-Forwarded-For` para descobrir o IP
real atrás do proxy da App Platform. `X-Forwarded-For` é forjável se a cadeia de
proxy confiáveis não for travada com exatidão — vira falsa sensação de segurança.
Filtrar antes de chegar na app é mais simples e mais robusto.

### Abordagem recomendada — Cloudflare na frente

A DigitalOcean App Platform sozinha não faz allowlist de IP por rota de forma
limpa. O caminho correto é colocar **Cloudflare** na frente dos subdomínios de
operador e restringir lá:

- **Cloudflare Access** (Zero Trust) nas zonas `admin.`, `pos.`, `kds.`,
  `gestor.`, `prod.`: política que só libera as faixas de IP da padaria/equipe
  (e, opcionalmente, identidade Google Workspace — já em uso no domínio).
- Ou, mais simples, **WAF / IP Access Rules** do Cloudflare bloqueando tudo que
  não está na allowlist para esses hostnames.
- A loja do cliente (apex) e a `api.` que ela consome **não** entram na
  allowlist — são públicas.

### Faixas de IP

Pendente do Pablo: as faixas de IP fixas da operação (loja física, casa,
VPN da equipe). Sem IP fixo, preferir Cloudflare Access por identidade
(Google Workspace) em vez de allowlist de IP.

### Fallback honesto (só se não houver ingress configurável)

Se em algum momento não der para usar ingress, um middleware app-level é
aceitável **apenas** lendo o IP da cadeia de proxy confiável conhecida da App
Platform (nunca o `X-Forwarded-For` cru), com a lista de proxies travada. Isso é
fallback, não o alvo.

---

## Checklist de go-live (operador)

- [ ] Piloto: titular concluiu autenticador e recuperação; proteção individual verificada em nova sessão.
- [ ] Antes de expansão global: todos os staff ativos inscritos e `check_admin_2fa_ready` verde; ativação coordenada.
- [ ] Superusers triviais de staging (`admin/admin`) **removidos** em prod
      (prod usa `bootstrap_admin` env-driven — ver [OPERATOR-AUTH-PLAN](../plans/completed/OPERATOR-AUTH-PLAN.md)).
- [ ] Cloudflare Access/WAF restringindo `admin.`/`pos.`/`kds.`/`gestor.`/`prod.`.
- [ ] `SESSION_COOKIE_DOMAIN` de produção configurado (auth cross-subdomínio).

---

## Referências

- [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md) — Lote C
- [OPERATOR-AUTH-PLAN](../plans/completed/OPERATOR-AUTH-PLAN.md) — auth cross-subdomínio (Opção C)
- [`middleware_2fa.py`](../../shopman/backstage/middleware_2fa.py) · [`setup_admin_totp`](../../shopman/backstage/management/commands/setup_admin_totp.py)
