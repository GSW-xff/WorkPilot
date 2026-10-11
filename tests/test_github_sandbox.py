from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx

from workpilot.github_sandbox import GitHubSandboxRunner, write_github_sandbox_report


class GitHubSandboxRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_runner_records_evidence_cleanup_and_token_revocation(self) -> None:
        issue: dict[str, object] | None = None
        comment: dict[str, object] | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal issue, comment
            path = request.url.path
            if request.method == "GET" and path == "/user":
                return httpx.Response(200, json={"id": 42, "login": "sandbox-user"})
            if path == "/applications/client-id/token":
                if request.method == "POST":
                    return httpx.Response(
                        200,
                        json={
                            "scopes": ["repo", "read:user"],
                            "app": {"name": "WorkPilot", "client_id": "client-id"},
                            "user": {"id": 42, "login": "sandbox-user"},
                        },
                    )
                return httpx.Response(204)
            if request.method == "GET" and path == "/repos/acme/sandbox":
                return httpx.Response(200, json={"full_name": "acme/sandbox", "private": True})
            if request.method == "GET" and path == "/search/issues":
                query = request.url.params.get("q", "")
                if issue and str(issue.get("body", "")).split("<!--")[-1].split(" -->")[0] in query:
                    return httpx.Response(200, json={"items": [issue]})
                comment_marker = (
                    str(comment.get("body", "")).split("<!--")[-1].split(" -->")[0]
                    if comment
                    else ""
                )
                if comment and comment_marker in query:
                    return httpx.Response(200, json={"items": [issue]})
                return httpx.Response(200, json={"items": []})
            if request.method == "POST" and path == "/repos/acme/sandbox/issues":
                body = json.loads(request.content)
                issue = {
                    "id": 101,
                    "number": 7,
                    "title": body["title"],
                    "state": "open",
                    "body": body["body"],
                    "html_url": "https://github.test/acme/sandbox/issues/7",
                }
                return httpx.Response(201, json=issue)
            if request.method == "POST" and path == "/repos/acme/sandbox/issues/7/comments":
                body = json.loads(request.content)
                comment = {
                    "id": 303,
                    "body": body["body"],
                    "html_url": "https://github.test/acme/sandbox/issues/7#issuecomment-303",
                }
                return httpx.Response(201, json=comment)
            if request.method == "DELETE" and path.endswith("/issues/comments/303"):
                return httpx.Response(204)
            if request.method == "PATCH" and path == "/repos/acme/sandbox/issues/7":
                return httpx.Response(200, json={**(issue or {}), "state": "closed"})
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        report = await GitHubSandboxRunner(
            client=client,
            api_base_url="https://api.github.test",
        ).run(
            repository="acme/sandbox",
            token="oauth-secret-token",
            client_id="client-id",
            client_secret="client-secret",
            webhook_secret="webhook-secret",
            inject_live_response_loss=False,
        )
        await client.aclose()

        self.assertFalse(report.passed)
        self.assertTrue(report.token_revoked)
        self.assertTrue(
            any(
                check.name == "oauth_token_remote_revocation"
                and check.status == "passed"
                for check in report.checks
            )
        )
        self.assertEqual([7], report.cleanup["closed_issues"])
        self.assertEqual([303], report.cleanup["deleted_comments"])
        self.assertEqual(2, len(report.remote_objects))
        self.assertTrue(
            any(check.name == "response_loss_after_remote_commit" for check in report.checks)
        )
        self.assertNotIn("oauth-secret-token", report.model_dump_json())
        with tempfile.TemporaryDirectory() as directory:
            paths = write_github_sandbox_report(report, Path(directory))
            self.assertIn("Secrets recorded: `false`", paths[1].read_text())

    async def test_keep_token_cannot_produce_a_passing_report(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/user":
                return httpx.Response(500)
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        report = await GitHubSandboxRunner(
            client=client,
            api_base_url="https://api.github.test",
        ).run(
            repository="acme/sandbox",
            token="oauth-secret-token",
            client_id="client-id",
            client_secret="client-secret",
            webhook_secret="webhook-secret",
            revoke_token=False,
            inject_live_response_loss=False,
        )
        await client.aclose()

        revocation = next(
            check
            for check in report.checks
            if check.name == "oauth_token_remote_revocation"
        )
        self.assertFalse(report.passed)
        self.assertFalse(report.token_revoked)
        self.assertEqual("not_run", revocation.status)
        self.assertEqual("disabled by --keep-token", revocation.details["reason"])


if __name__ == "__main__":
    unittest.main()
