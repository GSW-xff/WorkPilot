# OIDC authentication and RBAC

Production deployments set `WORKPILOT_AUTH_MODE=oidc` together with
`WORKPILOT_OIDC_ISSUER`, `WORKPILOT_OIDC_AUDIENCE` and `WORKPILOT_OIDC_JWKS_URL`.
The API validates RS256/ES256 signatures, issuer, audience, issued/expiry times,
subject and the custom `tenant_id` claim. The tenant header is ignored in this mode.

Tokens can carry `roles` as a JSON string array (or a space-delimited string) and
`scope` as an OAuth scope string. `approver` is required for approve/reject operations;
`admin` is required to revoke a connector and implies all roles. A task creator cannot
approve their own high-risk action. These checks implement a simple separation of duties.

The default `headers` mode is only intended for local development. It trusts
`X-Tenant-ID` and `X-User-ID` and grants all local roles so that the offline demo remains
easy to run. It must not be exposed to an untrusted network.
