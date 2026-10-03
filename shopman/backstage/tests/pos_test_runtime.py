"""Provisionamento sintético explícito para testes de PDV."""

from shopman.doorman.models import SubjectType, TrustedDevice

from shopman.backstage.station_trust import station_cookie_name


def bind_station(client, ref):
    device, token = TrustedDevice.create_for(subject_type=SubjectType.STATION, subject_id=ref)
    client.cookies[station_cookie_name(ref)] = token
    return device


def with_screen_total(payload: dict, channel_ref: str | None = None) -> dict:
    """O payload do fechamento com o total que a tela mostraria (D42).

    O PDV manda ``expected_total_q`` com o total da revisão; o teste que só quer
    fechar uma venda faz o mesmo, pela MESMA conta do servidor (preço carimbado,
    peso, desconto, taxa). Se a normalização recusar o payload, o fechamento
    recusa igual antes de olhar o total, e o valor mandado não importa.
    """
    if "expected_total_q" in payload:
        return payload
    from shopman.backstage.constants import POS_CHANNEL_REF
    from shopman.shop.services import pos as pos_service
    from shopman.shop.services import weighed_sale
    from shopman.shop.services.pos_intent import parse_pos_sale_intent

    ref = channel_ref or POS_CHANNEL_REF
    try:
        normalized = pos_service._inherit_sales_mode(ref, dict(payload))
        normalized = parse_pos_sale_intent(normalized, for_commit=True).payload
        channel, _config = pos_service._channel_and_config(ref)
        weighed_sale.apply_to_payload(normalized, channel=channel)
        pos_service._stamp_list_prices_from_session(
            normalized, pos_service._payload_open_tab_session(channel_ref=channel.ref, payload=normalized),
        )
        pos_service._ensure_resolved_prices(normalized)
        total_q = pos_service._payload_total_q(normalized)
    except Exception:
        total_q = 0
    return {**payload, "expected_total_q": total_q}
