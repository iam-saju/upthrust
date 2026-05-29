import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import Response

logger = logging.getLogger("upthrust.twilio")
router = APIRouter(prefix="/twilio")

SIP_URI = os.getenv("LIVEKIT_SIP_URI", "sip:+13367156229@4rgs9q6ucn9.sip.livekit.cloud")


@router.post("/call")
async def twilio_call_webhook(request: Request):
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    caller = form_data.get("From", "unknown")
    called = form_data.get("To", "unknown")
    logger.info("TWILIO_CALL from=%s to=%s CallSid=%s", caller, called, call_sid)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>{SIP_URI}</Sip>
    </Dial>
</Response>"""
    return Response(content=twiml, media_type="application/xml")
