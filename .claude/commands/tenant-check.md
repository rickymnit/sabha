Audit the codebase for tenant-isolation risks. Search apps/ and packages/ for:
- direct uses of `get_collection`, `db[`, `.find(`, `.aggregate(`, `.update_`, `.delete_` outside packages/core/sabha_core/repo.py
- queries or aggregation pipelines without a tenant_id match stage
- S3 keys built without the `{tenant_id}/` prefix
- cache keys, rate-limit keys or SSE channels without tenant_id
- endpoints that accept a recording/analysis/score id without checking it belongs to the caller's tenant

Report each finding with file:line, why it is a risk, and the fix. Then propose (do not yet write) a test in tests/security/test_tenant_isolation.py that would catch it. Scope: $ARGUMENTS
