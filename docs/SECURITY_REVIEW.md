# Obseil security review

A record of what was checked, what was found, and where each property is
enforced by a test rather than by intention.

Every item below has a corresponding assertion in
`backend/tests/api/test_security.py`, so a regression fails CI instead of
becoming an incident.

---

## Threat model

Obseil is a multi-tenant web application where each user uploads files that are
parsed by the server. The realistic threats, in order of likelihood:

1. **Cross-tenant data access** - one account reading another's projects,
   datasets, findings or reports. The highest-value target, and the easiest to
   get wrong.
2. **Malicious uploads** - path traversal via filename, resource exhaustion via
   size, or a parser exploited by crafted content.
3. **Credential attacks** - brute force, account enumeration, token forgery.
4. **Information disclosure** - stack traces, secrets in logs, internal paths.

Out of scope for the MVP: a compromised host, a compromised database, and
denial of service beyond the configured upload limit. Stated in
[SECURITY.md](../SECURITY.md).

---

## 1. Authentication

| Control | Where | Verified by |
| --- | --- | --- |
| Passwords hashed with bcrypt, per-password salt | `core/security.py` | `test_passwords_are_stored_hashed_and_salted` |
| Password never echoed in a response | `schemas/auth.py` | `test_passwords_are_never_returned` |
| Over-length passwords rejected, not silently truncated | `core/security.py` | `test_overlong_password_is_rejected_rather_than_truncated` |
| Malformed stored hash fails closed | `core/security.py` | `test_malformed_hash_fails_closed_instead_of_raising` |
| Work factor configurable, with a production floor | `core/config.py` | `test_production_refuses_a_weak_work_factor` |
| Repeated failed logins are rate limited | `core/ratelimit.py` | `TestLoginRateLimiting` |

**bcrypt is used directly, not through passlib**, which is unmaintained and
breaks against modern bcrypt releases.

**Over-length passwords are rejected rather than truncated.** bcrypt silently
ignores input beyond 72 bytes, which would mean two different long passwords
authenticating the same account.

### Account enumeration

An unknown email and a wrong password return **byte-identical** responses. When
the email is unknown, the service still verifies the submitted password against
a dummy hash so the response time does not give the answer away either.

That dummy hash is **generated at import from the configured work factor**, not
hardcoded. It used to be a literal pinned at cost 12, which was correct only
while the real cost also happened to be 12. Making the cost configurable
exposed the flaw: raise `OBSEIL_PASSWORD_HASH_ROUNDS` to 14 and the
unknown-email path would have become roughly four times faster than the
wrong-password path, restoring by the back door exactly the timing oracle this
dummy hash exists to close. `test_the_equal_timing_hash_matches_the_configured_cost`
now pins the two together.

- Enforced in `services/auth_service.py`
- Verified by `test_unknown_email_gives_the_same_error_as_a_wrong_password`
- Verified end to end by `e2e/tests/auth-and-errors.spec.ts`

### Rate limiting

Failed logins are counted per client address over a sliding five-minute window;
the eleventh is refused with **429 and a `Retry-After`** rather than checked.

The design decision worth stating is what is *not* counted. A counter keyed on
the submitted email would let anybody lock a chosen victim out of their own
account simply by submitting bad passwords for it. Keying on the caller means
an attacker can only ever rate-limit themselves.

| Property | Why |
| --- | --- |
| Only failures count | Signing in correctly never moves a legitimate user closer to a lockout |
| A success clears the count | Mistyping a password three times then getting it right leaves no residue |
| The limit applies before credentials are checked | Otherwise a correct guess would still be accepted, and the limit would not slow guessing at all |
| The 429 is identical for real and unknown accounts | A rate-limited response that differed would be a new enumeration oracle |
| The key table is LRU-bounded | An attacker cycling source addresses must not be able to grow it without limit - the limiter itself becoming the denial of service |

Two limitations, both deliberate:

- **Counts live in this process.** Correct for the single container this ships
  as; more than one replica needs shared storage behind the same `RateLimiter`
  interface, which is why that interface exists.
- **Users sharing one outbound address share a counter.** An office behind NAT
  may want `OBSEIL_LOGIN_MAX_ATTEMPTS` raised. Brute force needs thousands of
  attempts, so a generous limit still removes almost all of the risk.

Behind a reverse proxy the client address is the proxy unless uvicorn runs with
`--proxy-headers` and a trusted `--forwarded-allow-ips`. Obseil deliberately
does **not** parse `X-Forwarded-For` itself: any caller can set that header, so
trusting it unconditionally would let an attacker step around the limit by
inventing a new address per request.

A distributed attack across many addresses is not stopped here. That belongs at
the proxy or WAF layer, which can see the whole fleet.

---

## 2. Tokens

| Control | Verified by |
| --- | --- |
| Signature is validated; a tampered token is rejected | `test_a_tampered_token_is_rejected` |
| `alg: none` is rejected | `test_the_none_algorithm_is_rejected` |
| A token signed with another key is rejected | `test_token_signed_with_another_key_is_rejected` |
| A refresh token cannot be used as an access token | `test_refresh_token_is_not_accepted_as_an_access_token` |
| A token for a deleted account is rejected | `test_token_for_a_deleted_account_is_rejected` |
| A deactivated account cannot use an existing token | `test_deactivated_account_cannot_sign_in` |

Access and refresh tokens carry a distinct `type` claim, checked on decode, so
neither can be replayed at the other's endpoint. Refresh rotates the pair on
every use, limiting the window in which a stolen refresh token is useful.

**Accepted limitation:** tokens are stored in `localStorage`, so any script on
the origin can read them. This is the standard trade-off for a token-based SPA.
It is mitigated by short-lived access tokens (30 minutes by default) and by
shipping no third-party scripts. Moving to httpOnly cookies means changing
`services/tokenStore.ts` and the API's auth dependency - nothing else.

---

## 3. Authorisation

Every resource-scoped read and write funnels through one of three helpers -
`get_owned_project`, `get_owned_dataset`, `get_owned_analysis` - each of which
joins to `projects.owner_id`. There is no code path that loads one of these
objects by id without that join.

**Another user's resource returns 404, never 403.** A 403 confirms that the id
exists, which is itself information the caller has no right to.

One list, `SCOPED_ENDPOINTS`, names all **22 resource-scoped endpoints** and
drives three checks:

| Test | Asserts |
| --- | --- |
| `test_the_matrix_lists_every_scoped_route` | The list matches the router exactly |
| `test_every_scoped_endpoint_is_protected` | Each returns 404 for a signed-in non-owner |
| `test_every_scoped_endpoint_requires_a_token` | Each returns 401 with no token |

The first of those closes what used to be this design's one gap: adding a route
was previously enough to ship it untested, because the other two only checked
what somebody had remembered to write down. It now walks the router tree,
selects every path carrying an owned resource id (`project_id`, `dataset_id`,
`analysis_id`, `finding_id`), and fails if the list and the router disagree in
either direction - a missing entry, or a stale one for a route that is gone.

Introducing it immediately found three scoped endpoints that no test had ever
covered: `GET` and `PATCH /findings/{finding_id}`, and
`POST /projects/{project_id}/datasets` - uploading a dataset into someone
else's project. All three were correctly protected; none of them was proven to
be. That is the distinction the check exists to remove.

Two details make it trustworthy rather than decorative. It walks the router
rather than reading the OpenAPI schema, because a route hidden from the docs is
where a missing check would hide; and it asserts a floor on the number of
routes found, so that a FastAPI change that breaks the walk fails loudly
instead of passing with an empty set.

---

## 4. Uploads

This is the largest attack surface: the server parses files supplied by users.

| Control | Where | Verified by |
| --- | --- | --- |
| Storage keys are generated server-side from a UUID | `services/upload.py` | `test_the_storage_key_ignores_the_users_filename_entirely` |
| Filenames are sanitised for display only | `data/formats.py` | `test_strips_directory_components` |
| A second guard rejects any key that escapes the root | `storage/local.py` | `test_a_traversal_filename_cannot_escape_the_storage_root` |
| Size limit enforced while streaming | `services/upload.py` | `test_the_size_limit_is_enforced_while_streaming` |
| A rejected upload leaves nothing behind | `services/upload.py` | `test_an_oversized_upload_leaves_nothing_behind` |
| Extension whitelist, not blacklist | `data/formats.py` | `test_rejects_an_unsupported_extension` |
| Content is checked against the claimed format | `data/formats.py` | `test_rejects_a_csv_that_is_really_a_workbook` |

**Path traversal is removed from the threat model rather than sanitised away.**
The storage key is `projects/{uuid}/{uuid}.{ext}` - derived entirely from
server-side values. The user's filename never influences where bytes land; it
is kept only as a display string. The filesystem backend then independently
refuses any key that does not match a strict pattern or that resolves outside
the storage root.

**The size limit is enforced as the bytes arrive**, into a temporary file, so an
oversized upload never reaches permanent storage and a rejected one leaves no
orphan. An orphaned blob is also cleaned up if the database row cannot be
written.

**Operators should also enforce a body limit at the reverse proxy** - the
application limit protects storage, not the socket. Noted in
[SECURITY.md](../SECURITY.md).

### Parser exposure

pandas and openpyxl parse user-controlled content. Both are widely deployed and
actively maintained; the mitigation is dependency currency (Dependabot, weekly)
rather than sandboxing, which would be disproportionate for the MVP. Excel
formulas are never evaluated - `openpyxl` reads values, and Obseil never writes
a spreadsheet, so CSV-injection into an export is not applicable to the CSV
findings export either (it contains no user-controlled leading `=`, `+`, `-`,
`@` in a formula position because every field is quoted by `csv.DictWriter`).

---

## 5. Injection

SQLAlchemy binds every parameter; there is no string-interpolated SQL anywhere
in the codebase. `test_a_sql_payload_in_a_filter_is_treated_as_data` submits
`'; DROP TABLE projects; --` through the findings search filter and asserts the
table survives.

The API stores and returns text as text - it is not an HTML renderer, and
escaping is React's job at the point of rendering.
`test_a_script_payload_in_a_project_name_is_stored_verbatim` documents that
decision so nobody "fixes" it by escaping in the wrong layer.

---

## 6. Error disclosure

Every failure path returns the same envelope, with a `request_id` the user can
quote. Unhandled exceptions log a full traceback server-side and return a
generic `internal_error` - `test_an_unexpected_error_never_returns_a_traceback`
raises an exception containing `/etc/shadow` and asserts none of it reaches the
client.

Validation errors report the offending field, never the submitted value -
`test_validation_errors_do_not_echo_the_submitted_password`.

In `production`, the interactive API documentation and the OpenAPI schema are
disabled.

---

## 7. Configuration and secrets

| Control | Verified by |
| --- | --- |
| Production refuses to boot with the default secret | `test_production_refuses_to_boot_with_a_default_secret` |
| Production refuses to boot with `DEBUG` enabled | `test_production_refuses_to_boot_with_debug_enabled` |
| No secret is hardcoded outside `config.py` | `test_no_secret_is_hardcoded_outside_configuration` |

`.env` is gitignored; `.env.example` carries only placeholders and the command
to generate a real secret. The Docker Compose defaults are explicitly labelled
dev-only.

---

## 8. Transport and browser headers

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer` are set on every API response and by the nginx
config that serves the built frontend. CORS is restricted to the origins in
`OBSEIL_CORS_ORIGINS`, with no wildcard -
`test_cors_is_restricted_to_configured_origins` asserts an unlisted origin is
not echoed back.

TLS is terminated in front of the application; Obseil does not serve HTTPS
itself. Stated in [SECURITY.md](../SECURITY.md).

---

## 9. Containers

Both images run as an unprivileged user (`obseil`, uid 10001; `nginx` for the
web image), are multi-stage so build tooling is absent from the runtime layer,
and carry a healthcheck. `.dockerignore` excludes `.env`, tests and local state.

---

## Known gaps

Recorded rather than hidden. None is a blocker for an MVP; each is a
deliberate deferral.

| Gap | Why it is acceptable now | What would close it |
| --- | --- | --- |
| Rate limit counts live in one process | Correct for the single container Obseil ships as | A shared store behind the existing `RateLimiter` interface |
| Distributed brute force is not stopped | A per-address limit cannot see a botnet; the realistic single-host attack is stopped | A proxy or WAF rate limit across the fleet |
| Tokens in `localStorage` | Standard SPA trade-off, mitigated by short expiry and no third-party scripts | httpOnly refresh cookie + in-memory access token |
| No server-side token revocation | Stateless JWTs; logout is client-side | A revocation list keyed on the `jti` claim, which every token already carries |
| No audit log | Structured request logs cover the operational need | An append-only table of security-relevant actions |
