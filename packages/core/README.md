# packages/core

`sabha_core`, the shared foundation every Python app imports: validated settings from environment variables, the tenant-scoped MongoDB repository (the only way to read or write data; a query without `tenant_id` raises), domain models, the recording state machine, object-storage helpers, structured logging and telemetry setup.
