# File knowledge pipeline

WorkPilot accepts PDF, DOCX, XLSX, Markdown and UTF-8 text through
`POST /v1/knowledge/files`. The synchronous MVP pipeline records `PROCESSING`, `READY`
or `FAILED`, saves the immutable original in an object-store adapter, extracts bounded
sections, chunks them, and creates deterministic offline embeddings. The adapter boundary
can be replaced by S3/MinIO and a hosted embedding provider without changing the API.

Safety gates reject unsupported extensions, mismatched PDF/OOXML signatures, EICAR test
content, macros, oversized files, excessive archive expansion, excessive PDF pages and
large worksheets. Production should additionally put parsing in a resource-limited worker
and connect an antivirus daemon.

Every document and derived chunk carries `tenant_id`, owner and `private`/`tenant`
visibility. ACL filtering happens before ranking. Search combines lexical and vector ranks
with reciprocal-rank fusion and returns an auditable citation containing the source file,
page or sheet, chunk, preview and both component ranks. Retrieved text remains explicitly
`untrusted`; prompt-injection markers are surfaced rather than executed.

`GET /v1/knowledge/files/{id}/content` opens the original for citation verification.
`DELETE /v1/knowledge/files/{id}` removes the original plus chunks and embeddings. Only
the owner or an administrator can delete it.
