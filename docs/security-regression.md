# Agentic security regression

The versioned `evals/security_cases.jsonl` suite covers deterministic controls for prompt
injection, MCP description poisoning, excessive agency, OAuth scope escalation, tenant
isolation and secret leakage. Run `workpilot-security-eval` to reproduce the JSON and
Markdown reports under `evals/reports/security-v1`.

The current v1 policy suite contains 20 cases and passes 20/20. This number describes the
committed deterministic cases only. It is not a penetration-test result and does not claim
coverage of every OWASP Agentic threat. New incidents and user corrections should become
new regression rows instead of silently changing existing expected results.
