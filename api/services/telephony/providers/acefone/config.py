"""Acefone telephony configuration schemas."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AcefoneConfigurationRequest(BaseModel):
    """Request schema for Acefone configuration."""

    provider: Literal["acefone"] = Field(default="acefone")
    api_key: str = Field(..., description="Acefone API Key")
    endpoint_type: str = Field(default="static", description="static or dynamic")
    wss_url: Optional[str] = Field(default=None, description="WebSocket URL for static endpoint")
    did: Optional[str] = Field(default=None, description="DID number for inbound mapping")
    from_numbers: List[str] = Field(
        default_factory=list, description="List of phone numbers"
    )


class AcefoneConfigurationResponse(BaseModel):
    """Response schema for Acefone configuration with masked sensitive fields."""

    provider: Literal["acefone"] = Field(default="acefone")
    api_key: str  # Masked
    endpoint_type: str
    wss_url: Optional[str]
    did: Optional[str]
    from_numbers: List[str]
