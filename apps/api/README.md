# apps/api

The FastAPI service that the web app and integrations talk to. It holds the versioned `/v1` routers, request and response schemas, OIDC token validation, and thin services that call the tenant-scoped repository in `packages/core`. It authorises uploads and records intent but never touches audio bytes: clients upload straight to object storage with presigned multipart URLs. Errors are RFC 9457 problem+json, every create honours `Idempotency-Key`, and pagination is cursor-based.
