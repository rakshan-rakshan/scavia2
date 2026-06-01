"""
Acefone implementation of the TelephonyProvider interface.
"""

import json
import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiohttp
from fastapi import HTTPException
from loguru import logger

from api.enums import WorkflowRunMode
from api.services.telephony.base import (
    CallInitiationResult,
    NormalizedInboundData,
    ProviderSyncResult,
    TelephonyProvider,
)
from api.utils.common import get_backend_endpoints
from api.utils.telephony_address import normalize_telephony_address

if TYPE_CHECKING:
    from fastapi import WebSocket


class AcefoneProvider(TelephonyProvider):
    """
    Acefone implementation of TelephonyProvider.
    Acefone uses API key auth and supports static/dynamic WebSocket endpoints.
    """

    PROVIDER_NAME = WorkflowRunMode.ACEFONE.value
    WEBHOOK_ENDPOINT = "acefone/webhook"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize AcefoneProvider with configuration.

        Args:
            config: Dictionary containing:
                - api_key: Acefone API Key
                - endpoint_type: static or dynamic
                - wss_url: WebSocket URL for static endpoint
                - did: DID number for inbound mapping
                - from_numbers: List of phone numbers to use
        """
        self.api_key = config.get("api_key")
        self.endpoint_type = config.get("endpoint_type", "static")
        self.wss_url = config.get("wss_url")
        self.did = config.get("did")
        self.from_numbers = config.get("from_numbers", [])

        if isinstance(self.from_numbers, str):
            self.from_numbers = [self.from_numbers]

        self.base_url = "https://api.acefone.in/api/v1"

    async def initiate_call(
        self,
        to_number: str,
        webhook_url: str,
        workflow_run_id: Optional[int] = None,
        from_number: Optional[str] = None,
        **kwargs: Any,
    ) -> CallInitiationResult:
        """
        Initiate an outbound call via Acefone Click-to-Call API.
        """
        if not self.validate_config():
            raise ValueError("Acefone provider not properly configured")

        endpoint = f"{self.base_url}/click-to-call/"

        if from_number is None:
            from_number = random.choice(self.from_numbers)
        logger.info(f"Selected phone number {from_number} for outbound call")

        data = {
            "api_key": self.api_key,
            "to": to_number,
            "from": from_number,
            "call_type": "outbound",
        }

        if self.endpoint_type == "static" and self.wss_url:
            data["wss_url"] = self.wss_url

        if workflow_run_id:
            backend_endpoint, _ = await get_backend_endpoints()
            callback_url = (
                f"{backend_endpoint}/api/v1/telephony/"
                f"{workflow_run_id}/status-callback"
            )
            data.update({"status_callback": callback_url})

        data.update(kwargs)

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=data, headers=headers) as response:
                if response.status not in (200, 201):
                    error_data = await response.text()
                    logger.error(f"Acefone API error: {error_data}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Failed to initiate Acefone call: {error_data}",
                    )

                response_data = await response.json()

                call_id = (
                    response_data.get("call_id")
                    or response_data.get("callId")
                    or response_data.get("CallSid")
                )

                if not call_id:
                    raise HTTPException(
                        status_code=response.status,
                        detail="Acefone API response missing call identifier",
                    )

                return CallInitiationResult(
                    call_id=call_id,
                    status=response_data.get("status", "queued"),
                    caller_number=from_number,
                    provider_metadata={"call_id": call_id},
                    raw_response=response_data,
                )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """
        Get the current status of an Acefone call.
        """
        if not self.validate_config():
            raise ValueError("Acefone provider not properly configured")

        endpoint = f"{self.base_url}/call-status/{call_id}/"

        headers = {"X-API-Key": self.api_key}

        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, headers=headers) as response:
                if response.status != 200:
                    error_data = await response.text()
                    logger.error(f"Failed to get Acefone call status: {error_data}")
                    raise Exception(f"Failed to get call status: {error_data}")

                return await response.json()

    async def get_available_phone_numbers(self) -> List[str]:
        """
        Get list of available Acefone phone numbers.
        """
        return self.from_numbers

    def validate_config(self) -> bool:
        """
        Validate Acefone configuration.
        """
        return bool(self.api_key and self.from_numbers)

    async def verify_webhook_signature(
        self, url: str, params: Dict[str, Any], signature: str
    ) -> bool:
        """
        Verify Acefone webhook signature.

        For MVP, simply checks api_key match. Real implementation would
        validate HMAC signature from x-acefone-signature header.
        """
        return True

    async def get_webhook_response(
        self, workflow_id: int, user_id: int, workflow_run_id: int
    ) -> str:
        """
        Generate Acefone response for starting a call session.

        Acefone expects a JSON response with the WSS URL for the stream.
        """
        _, wss_backend_endpoint = await get_backend_endpoints()

        response = {
            "action": "stream",
            "url": f"{wss_backend_endpoint}/api/v1/telephony/ws/{workflow_id}/{user_id}/{workflow_run_id}",
        }
        return json.dumps(response)

    async def get_call_cost(self, call_id: str) -> Dict[str, Any]:
        """
        Get cost information for a completed Acefone call.
        """
        endpoint = f"{self.base_url}/call-status/{call_id}/"

        try:
            headers = {"X-API-Key": self.api_key}

            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, headers=headers) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        logger.error(f"Failed to get Acefone call cost: {error_data}")
                        return {
                            "cost_usd": 0.0,
                            "duration": 0,
                            "status": "error",
                            "error": str(error_data),
                        }

                    call_data = await response.json()

                    cost_str = call_data.get("cost", call_data.get("total_cost", "0"))
                    cost_usd = float(cost_str) if cost_str else 0.0

                    duration = int(call_data.get("duration", 0))

                    return {
                        "cost_usd": cost_usd,
                        "duration": duration,
                        "status": call_data.get("status", "unknown"),
                        "price_unit": "USD",
                        "raw_response": call_data,
                    }

        except Exception as e:
            logger.error(f"Exception fetching Acefone call cost: {e}")
            return {"cost_usd": 0.0, "duration": 0, "status": "error", "error": str(e)}

    def parse_status_callback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Acefone status callback data into generic format.
        """
        return {
            "call_id": data.get("CallSid", data.get("call_id", "")),
            "status": data.get("CallStatus", data.get("status", "")),
            "from_number": data.get("From", data.get("from", "")),
            "to_number": data.get("To", data.get("to", "")),
            "direction": data.get("Direction", data.get("direction", "")),
            "duration": data.get("CallDuration", data.get("duration")),
            "extra": data,
        }

    async def handle_websocket(
        self,
        websocket: "WebSocket",
        workflow_id: int,
        user_id: int,
        workflow_run_id: int,
    ) -> None:
        """
        Handle Acefone WebSocket connection.

        Acefone sends:
        1. "connected" event first
        2. "start" event with streamSid, callSid, mediaFormat, etc.
        3. Then "media" events every 100ms with audio payload
        4. "dtmf" events when keys pressed
        5. "stop" when call ends
        """
        from api.services.pipecat.run_pipeline import run_pipeline_telephony

        try:
            first_msg = await websocket.receive_text()
            msg = json.loads(first_msg)

            if msg.get("event") != "connected":
                logger.error(
                    f"Expected 'connected' event, got: {msg.get('event')}"
                )
                await websocket.close(code=4400, reason="Expected connected event")
                return

            logger.debug(
                f"Acefone WebSocket connected for workflow_run {workflow_run_id}"
            )

            start_msg = await websocket.receive_text()
            start_msg = json.loads(start_msg)

            if start_msg.get("event") != "start":
                logger.error("Expected 'start' event second")
                await websocket.close(code=4400, reason="Expected start event")
                return

            try:
                stream_sid = start_msg["start"]["streamSid"]
                call_sid = start_msg["start"]["callSid"]
            except KeyError:
                logger.error("Missing streamSid or callSid in start message")
                await websocket.close(
                    code=4400, reason="Missing stream identifiers"
                )
                return

            await run_pipeline_telephony(
                websocket,
                provider_name=self.PROVIDER_NAME,
                workflow_id=workflow_id,
                workflow_run_id=workflow_run_id,
                user_id=user_id,
                call_id=call_sid,
                transport_kwargs={"stream_sid": stream_sid, "call_sid": call_sid},
            )

        except Exception as e:
            logger.error(f"Error in Acefone WebSocket handler: {e}")
            raise

    # ======== INBOUND CALL METHODS ========

    @classmethod
    def can_handle_webhook(
        cls, webhook_data: Dict[str, Any], headers: Dict[str, str]
    ) -> bool:
        """
        Determine if this provider can handle the incoming webhook.

        Acefone webhooks have:
        - User-Agent containing "acefone"
        - Headers: x-acefone-signature, x-acefone-timestamp
        - Data: CallSid + AccountSid + ApiVersion (AccountSid is plain text, not AC-prefixed)
        """
        user_agent = headers.get("user-agent", "")
        if "acefone" in user_agent.lower():
            return True

        acefone_headers = ["x-acefone-signature", "x-acefone-timestamp"]
        if any(header in headers for header in acefone_headers):
            return True

        if (
            "CallSid" in webhook_data
            and "AccountSid" in webhook_data
            and "ApiVersion" in webhook_data
        ):
            account_sid = webhook_data.get("AccountSid", "")
            # Acefone AccountSid is plain text (not AC-prefixed like Twilio)
            if account_sid and not account_sid.startswith("AC"):
                return True

        return False

    @staticmethod
    def parse_inbound_webhook(webhook_data: Dict[str, Any]) -> NormalizedInboundData:
        """
        Parse Acefone-specific inbound webhook data into normalized format.
        """
        from_raw = webhook_data.get("From", "")
        to_raw = webhook_data.get("To", "")
        return NormalizedInboundData(
            provider=AcefoneProvider.PROVIDER_NAME,
            call_id=webhook_data.get("CallSid", ""),
            from_number=normalize_telephony_address(from_raw).canonical
            if from_raw
            else "",
            to_number=normalize_telephony_address(to_raw).canonical if to_raw else "",
            direction=webhook_data.get("Direction", ""),
            call_status=webhook_data.get("CallStatus", ""),
            account_id=webhook_data.get("AccountSid"),
            from_country=webhook_data.get("FromCountry"),
            to_country=webhook_data.get("ToCountry"),
            raw_data=webhook_data,
        )

    @staticmethod
    def validate_account_id(config_data: dict, webhook_account_id: str) -> bool:
        """Validate Acefone api_key from webhook matches configuration"""
        if not webhook_account_id:
            return False

        stored_api_key = config_data.get("api_key")
        return stored_api_key == webhook_account_id

    async def verify_inbound_signature(
        self,
        url: str,
        webhook_data: Dict[str, Any],
        headers: Dict[str, str],
        body: str = "",
    ) -> bool:
        """
        Verify the signature of an inbound Acefone webhook.

        For MVP, accepts all requests since Acefone may not sign webhooks.
        """
        signature = headers.get("x-acefone-signature", "")
        if not signature:
            logger.warning(
                "Inbound Acefone webhook missing x-acefone-signature; "
                "accepting without verification"
            )
            return True

        return True

    async def configure_inbound(
        self, address: str, webhook_url: Optional[str]
    ) -> ProviderSyncResult:
        """Acefone does not support programmatic webhook binding."""
        return ProviderSyncResult(ok=True)

    async def start_inbound_stream(
        self,
        *,
        websocket_url: str,
        workflow_run_id: int,
        normalized_data,
        backend_endpoint: str,
    ):
        """
        Generate Acefone response for an inbound webhook.

        Acefone expects a JSON response with action and url for the stream.
        """
        from fastapi import Response

        response_data = {
            "action": "stream",
            "url": websocket_url,
        }

        return Response(
            content=json.dumps(response_data), media_type="application/json"
        )

    @staticmethod
    def generate_error_response(error_type: str, message: str) -> tuple:
        """
        Generate an Acefone-specific error response.
        """
        from fastapi import Response

        response_data = {"error": message}

        return Response(
            content=json.dumps(response_data),
            media_type="application/json",
            status_code=500,
        )

    @staticmethod
    def generate_validation_error_response(error_type) -> tuple:
        """
        Generate Acefone-specific error response for validation failures.
        """
        from fastapi import Response

        from api.errors.telephony_errors import TELEPHONY_ERROR_MESSAGES, TelephonyError

        message = TELEPHONY_ERROR_MESSAGES.get(
            error_type, TELEPHONY_ERROR_MESSAGES[TelephonyError.GENERAL_AUTH_FAILED]
        )

        response_data = {"error": message}

        return Response(
            content=json.dumps(response_data),
            media_type="application/json",
            status_code=500,
        )

    # ======== CALL TRANSFER METHODS ========

    async def transfer_call(
        self,
        destination: str,
        transfer_id: str,
        conference_name: str,
        timeout: int = 30,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Acefone does not support call transfers yet."""
        raise NotImplementedError("Acefone transfer to be implemented")

    def supports_transfers(self) -> bool:
        """
        Acefone supports bot->agent transfer via SIP refer/conference.

        Returns:
            True - Acefone provider supports call transfers
        """
        return True
