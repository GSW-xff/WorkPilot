# Deployment and software supply chain

The Helm chart under `deploy/helm/workpilot` separates the API and Temporal worker into
independent Deployments. It includes API startup/readiness/liveness probes, worker process
health, resource requests and limits, PodDisruptionBudgets, default-restricted networking,
non-root execution, dropped capabilities and a read-only root filesystem.

Optional KEDA scaling uses Temporal task-queue backlog from Prometheus instead of CPU.
The database URL remains a Secret reference. Migrations should run as a separate owner-role
job before promoting the same immutable image digest; application pods never receive the
migration credential.

`.github/workflows/supply-chain.yml` adds CodeQL, pull-request dependency review, Trivy
HIGH/CRITICAL image scanning, an SPDX JSON SBOM, GitHub artifact attestation and Helm
lint/render checks. These workflow definitions are committed controls; they become evidence
only after the repository's GitHub Actions run succeeds. Attestation proves provenance, not
absence of vulnerabilities.

Terraform is intentionally absent: the project has no selected cloud or real managed
resources, and empty demonstration IaC would contradict the V3 plan. Add it only alongside
an actual staging environment and its state/ownership decision.

## Local verification (2026-10-10)

- Helm 3.17.3 lint: `1 chart(s) linted, 0 chart(s) failed`;
- Helm template with KEDA enabled and an immutable SHA-256 image reference: rendered;
- Docker image: built successfully;
- runtime: started as UID/GID 10001 with a read-only root filesystem and bounded `/tmp`;
- `/health`: `200`, reporting the expected fake-enterprise/memory local profile.

The GitHub-only CodeQL, Trivy and attestation jobs are not marked as passed until the remote
workflow actually runs.
