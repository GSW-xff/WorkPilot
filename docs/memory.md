# Governed memory

WorkPilot separates memory into three explicit layers:

- working memory is the current `TaskRun`, checkpoint and Temporal state;
- episodic memory is a structured summary created only from a terminal task;
- semantic memory is the ACL-filtered file knowledge and citation pipeline.

Long-term `MemoryRecord` values always include tenant, owner, source references, source
trust, TTL and confidence. Untrusted external content cannot be written unless a user has
explicitly confirmed it. Expired records are purged before reads. Owners can inspect,
correct and delete records in the console; administrators remain tenant-bound.

The API is `/v1/memories`, with `POST /v1/memories/from-task/{task_id}` for a terminal
task summary. It intentionally does not store unlimited chat transcripts or silently learn
from retrieved documents.
