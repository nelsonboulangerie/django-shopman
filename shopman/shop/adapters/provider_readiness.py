"""Read provider readiness through the Backstage integration boundary."""


def build_provider_readiness(*, mode: str):
    from shopman.backstage.services.integration_readiness import build_provider_readiness as build

    return build(mode=mode)
