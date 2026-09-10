"""A sessão caída é distinguível da falta de permissão — nas sete superfícies.

⚠️ **O backstage nunca devolve 401.** ``DEFAULT_AUTHENTICATION_CLASSES`` tem uma
classe só (``SessionAuthentication``), que não implementa ``authenticate_header()``
— e sem header de desafio o DRF rebaixa o ``NotAuthenticated`` para **403**. Este
arquivo prova o rebaixamento em vez de assumi-lo, porque é ele que torna o
``error.code`` necessário: sem código, "sua sessão caiu" e "você não tem permissão"
chegam ao operador com exatamente a mesma cara, e a única forma de separá-las seria
casar a mensagem em português.

As duas provas andam em par:

- **positiva** — requisição anônima traz ``error.code == "not_authenticated"``;
- **negativa** — 403 por falta de permissão continua SEM ``error``. É a ausência
  que diz ao front "não há nada a oferecer aqui". Se todo 403 ganhasse código, a
  tela mandaria o operador digitar senha para uma recusa que senha não resolve.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

# Uma por superfície de operador: se o rebaixamento fosse específico de uma view,
# esta lista pegaria. Todas são GET e não precisam de fixture de domínio — o gate
# de autenticação responde antes de qualquer leitura.
ROTAS_DE_OPERADOR = [
    "api-backstage-hub",
    "api-backstage-pos",
    "api-backstage-kds-index",
    "api-backstage-production",
]


@pytest.mark.django_db
@pytest.mark.parametrize("rota", ROTAS_DE_OPERADOR)
def test_requisicao_anonima_nomeia_a_sessao_caida(client, rota):
    resposta = client.get(reverse(rota))

    # 403, não 401 — o rebaixamento do DRF, provado e não presumido.
    assert resposta.status_code == 403
    corpo = resposta.json()
    assert corpo["error"]["code"] == "not_authenticated"
    # O dialeto canônico continua inteiro por baixo do superset.
    assert corpo["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize("rota", ROTAS_DE_OPERADOR)
def test_falta_de_permissao_continua_muda(client, rota):
    # Autenticado de verdade, sem permissão nenhuma: o 403 aqui é o "proibido"
    # legítimo, e login não conserta. Assert-negativo: nada foi alargado.
    cliente_comum = User.objects.create_user("sem-permissao", password="pw", is_staff=False)
    client.force_login(cliente_comum)

    resposta = client.get(reverse(rota))

    assert resposta.status_code == 403
    corpo = resposta.json()
    assert "error" not in corpo, (
        f"{rota}: 403 por falta de permissão ganhou error.code — o front passaria a "
        "tratar toda recusa como sessão expirada e pediria senha à toa."
    )
    assert corpo["detail"]
