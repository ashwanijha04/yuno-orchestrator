"""PIIRedactionInterceptor — scrubs obvious PII (emails, phone numbers) from a
response after the call. A regex stub for the demo; production swaps in Presidio
or a model-based filter behind the same interceptor seam."""

from __future__ import annotations

import re

from app.harness.call import HarnessedCall
from app.harness.interceptors.base import InterceptorDecision

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)\d{3}[\s-]?\d{4}\b")


class PIIRedactionInterceptor:
    name = "pii_redact"

    async def before(self, call: HarnessedCall) -> InterceptorDecision:
        return InterceptorDecision(action="continue")

    async def after(self, call: HarnessedCall) -> None:
        if call.response and call.response.content:
            redacted = _EMAIL.sub("[redacted-email]", call.response.content)
            redacted = _PHONE.sub("[redacted-phone]", redacted)
            call.response.content = redacted
