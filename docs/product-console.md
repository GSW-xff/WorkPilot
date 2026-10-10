# Product console

The dependency-free web console at `/` covers the complete local product loop:

- local organization/user switching or a production OIDC bearer token;
- reusable task templates, status filtering, plan DAG and live timeline polling;
- an approval inbox with risk, parameter preview, plan version and parameter hash;
- artifacts, audit-package export and structured user feedback;
- file upload, index state, hybrid retrieval, source locator and original-file preview;
- UNKNOWN/RETRYABLE recovery cases with links back to full task evidence;
- GitHub OAuth authorization, scope display and revocation;
- versioned Agent and retrieval evaluation reports with confidence intervals.

The page intentionally uses the existing FastAPI surface and no frontend build step so a
reviewer can start the repository and inspect the product immediately. Production OIDC
tokens must come from the configured IdP; the console does not mint or persist credentials
beyond browser `sessionStorage`. Local header identity mode is visibly labelled as
development-only.
