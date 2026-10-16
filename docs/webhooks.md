# Sabha webhooks

For developers who receive Sabha events in their own systems. A school or company configures an HTTPS endpoint and
receives a `POST` when a recording finishes.

## Events

| Type | When | Body (JSON) |
| --- | --- | --- |
| `recording.completed` | A recording's report is ready | `{"type", "event_id", "tenant_id", "recording_id", "occurred_at"}` |

Bodies never contain scores, quotes or transcript text. Fetch those from the API with your own credentials.
`event_id` is unique per event; the same event may be delivered more than once, so ignore an `event_id` you have
already processed.

## Verifying the signature

Every request carries a header:

```
Sabha-Signature: t=1760000000,v1=5f2b...e9
```

- `t` is the time Sabha signed the request, in Unix seconds.
- `v1` is the hex HMAC-SHA256 of the string `"<t>." + <raw request body>`, keyed with your endpoint's signing secret.

To verify:

1. Read the **raw** body bytes before any JSON parsing (re-serialised JSON will not match).
2. Compute `HMAC-SHA256(secret, "<t>." + body)` and compare it with `v1` using a constant-time comparison.
3. Reject the request if `t` is more than 5 minutes from your clock, to stop replays.

```python
import hashlib, hmac, time

def verify(body: bytes, header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, signature = int(parts["t"]), parts["v1"]
    if abs(time.time() - t) > 300:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

Sabha's own implementation is `apps/workers/sabha_workers/notifications/webhooks.py`.

## Retries

Respond with any `2xx` status within 10 seconds to acknowledge. Otherwise Sabha retries with exponential backoff,
starting at 30 seconds and doubling up to 2 hours between attempts, for up to 24 hours; after that the delivery is
marked failed in the tenant's delivery log.
