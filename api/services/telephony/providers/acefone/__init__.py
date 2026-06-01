"""Acefone telephony provider package."""

from typing import Any, Dict

from api.services.telephony.registry import (
    ProviderSpec,
    ProviderUIField,
    ProviderUIMetadata,
    register,
)

from .config import AcefoneConfigurationRequest, AcefoneConfigurationResponse
from .provider import AcefoneProvider
from .transport import create_transport


def _config_loader(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": "acefone",
        "api_key": value.get("api_key"),
        "endpoint_type": value.get("endpoint_type", "static"),
        "wss_url": value.get("wss_url"),
        "did": value.get("did"),
        "from_numbers": value.get("from_numbers", []),
    }


_UI_METADATA = ProviderUIMetadata(
    display_name="Acefone",
    docs_url="https://docs.acefone.in/docs/bi-directional-audio-streaming-integration-document",
    fields=[
        ProviderUIField(
            name="api_key",
            label="API Key",
            type="password",
            sensitive=True,
            description="Acefone API Key",
        ),
        ProviderUIField(
            name="endpoint_type",
            label="Endpoint Type",
            type="text",
            description="static or dynamic",
        ),
        ProviderUIField(
            name="wss_url",
            label="WebSocket URL",
            type="text",
            required=False,
            description="WebSocket URL for static endpoint",
        ),
        ProviderUIField(
            name="did",
            label="DID Number",
            type="text",
            required=False,
            description="DID number for inbound mapping",
        ),
    ],
)


SPEC = ProviderSpec(
    name="acefone",
    provider_cls=AcefoneProvider,
    config_loader=_config_loader,
    transport_factory=create_transport,
    transport_sample_rate=8000,
    config_request_cls=AcefoneConfigurationRequest,
    ui_metadata=_UI_METADATA,
    config_response_cls=AcefoneConfigurationResponse,
    account_id_credential_field="api_key",
)


register(SPEC)


__all__ = [
    "SPEC",
    "AcefoneConfigurationRequest",
    "AcefoneConfigurationResponse",
    "AcefoneProvider",
    "create_transport",
]
