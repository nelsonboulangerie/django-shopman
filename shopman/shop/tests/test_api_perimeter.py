"""Perímetro das APIs do kernel — guardrail de segurança.

Os pacotes do kernel (orderman, offerman, stockman, craftsman, guestman)
expõem ViewSets DRF de CRUD com o default global `IsAuthenticated`. Como clientes
do storefront viram usuários Django autenticados (login OTP chama `login()`), montar
essas rotas no deployment deixaria qualquer cliente logado ler/mutar dados do kernel
(sessões e comandas POS, base de PII, ledger de estoque, BOM).

Nenhuma superfície consome essas rotas — os apps Nuxt entram por `api/v1/` (storefront)
e `api/v1/backstage/` (projections gateadas por permissão). Elas foram desmontadas do
`config/urls.py`. Este teste trava a re-introdução silenciosa.

O `payman` saiu da lista porque não tem mais pacote `api/`: era código morto no
deployment cuja única trava era `IsAuthenticated` (qualquer cliente logado
listaria os intents da loja e filtraria por `order_ref` alheio). A superfície de
pagamento do operador é o Admin (`payman.contrib.admin_unfold`, leitura) mais a
reconciliação financeira diária do backstage. O guardrail virou ausência do
módulo, abaixo.

Contrato: se um dia uma dessas superfícies ganhar consumidor real, ela volta COM
permissão explícita (`IsAdminUser`/`DjangoModelPermissions`) e este guardrail é
atualizado deliberadamente — nunca por reflexo.
"""

from pathlib import Path

import pytest
from django.urls import get_resolver

# Prefixos de CRUD do kernel que NÃO podem estar montados no deployment.
UNMOUNTED_KERNEL_API_PREFIXES = [
    "api/orderman/",
    "api/offerman/",
    "api/stockman/",
    "api/craftsman/",
    "api/customers/",
]

# Prefixos que DEVEM continuar montados (consumidos pelas superfícies/BFF).
MOUNTED_SURFACE_API_PREFIXES = [
    "api/v1/",          # storefront headless (BFF do cliente)
    "api/v1/backstage/",  # projections gateadas dos apps operador (Nuxt)
]


def _mounted_prefixes() -> set[str]:
    """Coleta os prefixos de include de 1º nível do ROOT_URLCONF (regex → texto)."""
    prefixes = set()
    for pattern in get_resolver().url_patterns:
        # URLResolver (include) tem .url_patterns; extraímos o prefixo textual do regex.
        regex = getattr(pattern.pattern, "regex", None)
        if regex is None:
            continue
        # `^api/orderman/` → `api/orderman/`
        prefixes.add(regex.pattern.lstrip("^"))
    return prefixes


@pytest.mark.parametrize("prefix", UNMOUNTED_KERNEL_API_PREFIXES)
def test_kernel_crud_api_is_not_mounted(prefix):
    """Nenhum include do ROOT_URLCONF cobre um prefixo de CRUD do kernel."""
    mounted = _mounted_prefixes()
    assert prefix not in mounted, (
        f"{prefix} está montado no config/urls.py. APIs de CRUD do kernel não podem "
        "ser expostas no deployment — são superfície de ataque sem consumidor "
        "(clientes têm sessão Django). Ver test_api_perimeter."
    )


def test_payman_has_no_api_package():
    """O Payman não tem superfície HTTP própria — nem desmontada.

    Dado de pagamento é o mais sensível do sistema e não tem consumidor por
    HTTP direto: o que o operador precisa vem do Admin e das projections do
    backstage. Um pacote `api/` parado no repositório é só um plug esperando
    tomada.
    """
    import shopman.payman

    # Olha o diretório do pacote em uso, não ``find_spec``: num worktree, o
    # finder do editable install responde pelo checkout principal e o teste
    # falaria de outra árvore.
    api_dir = Path(shopman.payman.__path__[0]) / "api"
    assert not api_dir.exists(), (
        f"{api_dir} voltou a existir. Superfície HTTP de pagamento só com "
        "consumidor real E permissão explícita — ver test_api_perimeter."
    )


@pytest.mark.parametrize("prefix", MOUNTED_SURFACE_API_PREFIXES)
def test_surface_api_stays_mounted(prefix):
    """As APIs de superfície seguem montadas — pega remoção acidental."""
    mounted = _mounted_prefixes()
    assert prefix in mounted, (
        f"{prefix} não está mais montado no config/urls.py — uma superfície viva "
        "(BFF/Nuxt) foi desmontada por engano."
    )
