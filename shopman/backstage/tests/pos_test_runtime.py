"""Provisionamento sintético explícito para testes de PDV."""

from shopman.doorman.models import SubjectType, TrustedDevice

from shopman.backstage.station_trust import station_cookie_name


def bind_station(client, ref):
    device, token = TrustedDevice.create_for(subject_type=SubjectType.STATION, subject_id=ref)
    client.cookies[station_cookie_name(ref)] = token
    return device
