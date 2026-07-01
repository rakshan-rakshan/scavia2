"""Server-side post-call lead delivery and CRM logging.

Two complementary post-call hooks:

``log_call_to_supabase``
    Writes **every** completed telephony call to the shared Supabase ``leads``
    table (gated by ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY`` + workflow
    allowlist). Runs unconditionally — no outcome filter.

``deliver_lead_for_run``
    POSTs to the Google Sheet webhook, but **only** when the call resulted in a
    confirmed site visit (``visit_datetime`` present in gathered_context).
    The Sheet payload includes all lead fields plus the new ``intent`` and
    ``visit_datetime`` fields.

Both are best-effort and never raise into the caller.
"""

from api.services.lead_delivery.delivery import (
    build_lead_payload,
    deliver_lead_for_run,
)
from api.services.lead_delivery.supabase_logger import (
    build_supabase_payload,
    log_call_to_supabase,
)

__all__ = [
    "build_lead_payload",
    "deliver_lead_for_run",
    "build_supabase_payload",
    "log_call_to_supabase",
]
