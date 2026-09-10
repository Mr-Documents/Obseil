"""Getting a freshly issued token pair from the callback into the SPA.

The callback is a browser redirect, so the only things that can carry data back
to the frontend are the URL and cookies. Putting the tokens in the URL - query
or fragment - leaves them in browser history, and in the fragment's case in
every extension that can read the address bar.

Instead the callback hands over a **single-use code with a one-minute life**.
The SPA posts it straight back and receives the tokens in a response body that
is never written down anywhere. A code that leaks is worthless the moment it is
redeemed, and worthless a minute later regardless.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable

from app.schemas.auth import TokenPair

#: Long enough for a redirect and one request, short enough that an abandoned
#: code is meaningless before anyone could find it.
CODE_TTL_SECONDS = 60

#: Bounds memory if codes are minted and never redeemed.
MAX_PENDING_CODES = 10_000


class HandoffStore:
    """Short-lived, single-use codes mapped to token pairs.

    In-process, like the login rate limiter and for the same reason: this is
    correct for the single container Obseil ships as. More than one replica
    needs shared storage, and the redemption must stay atomic there too -
    "read then delete" as two steps would let one code be spent twice.
    """

    def __init__(
        self, *, ttl_seconds: float = CODE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._codes: dict[str, tuple[float, TokenPair]] = {}

    def _drop_expired(self, now: float) -> None:
        for code in [c for c, (expiry, _) in self._codes.items() if expiry <= now]:
            del self._codes[code]

    def issue(self, tokens: TokenPair) -> str:
        now = self._clock()
        code = secrets.token_urlsafe(32)
        with self._lock:
            self._drop_expired(now)
            if len(self._codes) >= MAX_PENDING_CODES:
                # Drop the oldest rather than refuse a legitimate sign-in.
                oldest = min(self._codes, key=lambda c: self._codes[c][0])
                del self._codes[oldest]
            self._codes[code] = (now + self._ttl, tokens)
        return code

    def redeem(self, code: str) -> TokenPair | None:
        """Spend ``code``, or return ``None`` if it is unknown or expired.

        The lookup and the removal happen under one lock, so two requests
        racing on the same code cannot both be served.
        """
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            entry = self._codes.pop(code, None)
        if entry is None:
            return None
        return entry[1]

    def clear(self) -> None:
        with self._lock:
            self._codes.clear()


handoff_store = HandoffStore()
