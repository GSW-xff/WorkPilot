from __future__ import annotations

import tomllib
from pathlib import Path

import workpilot
from workpilot.resources import bundled_path

ROOT = Path(__file__).resolve().parents[1]


def test_public_repository_has_community_and_release_files() -> None:
    required = (
        "LICENSE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        ".dockerignore",
        ".editorconfig",
        ".gitattributes",
        ".github/dependabot.yml",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        "docs/github-publishing.md",
    )

    for relative_path in required:
        assert (ROOT / relative_path).is_file(), relative_path


def test_local_secrets_and_generated_artifacts_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in (".env", "*.db", "dist/", ".~*", "evals/model-profiles.local.json"):
        assert pattern in gitignore
    for pattern in (".git", ".env", "*.db", ".venv", "docs", "tests"):
        assert pattern in dockerignore


def test_env_example_is_safe_for_an_offline_demo() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "WORKPILOT_PLANNER_MODE=demo" in content
    assert "WORKPILOT_MODEL_API_KEY=" in content
    assert "WORKPILOT_GITHUB_CLIENT_SECRET=" in content
    assert "\nWORKPILOT_DATABASE_URL=" not in content
    assert "\nWORKPILOT_TEMPORAL_TARGET=" not in content


def test_package_metadata_matches_runtime_version_and_license() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert metadata["version"] == workpilot.__version__
    assert metadata["license"]["file"] == "LICENSE"
    assert "License :: OSI Approved :: MIT License" in metadata["classifiers"]


def test_installable_package_declares_runtime_assets() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]

    assert {"workpilot", "apps", "benchmarks", "evals"} <= set(packages)
    assert bundled_path("apps", "web", "index.html").is_file()
    assert bundled_path("evals", "datasets", "workpilot-v1.jsonl").is_file()
    assert bundled_path("evals", "retrieval_cases.jsonl").is_file()
    assert bundled_path("evals", "security_cases.jsonl").is_file()


def test_readme_links_to_repository_policies_and_publishing_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for link in ("CONTRIBUTING.md", "SECURITY.md", "docs/github-publishing.md", "LICENSE"):
        assert link in readme
