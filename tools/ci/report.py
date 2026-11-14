"""Publish one sticky PR comment using data artifacts, never PR code."""

import argparse
import json
import os
import re

from tools.ci.common import api, pages

MARKER = "<!-- ghost-skill-submission -->"
LABELS = {
    "skill-submission",
    "has-python",
    "soft-skill",
    "needs-security-review",
    "size/small",
    "size/medium",
    "size/large",
}


def render(results, trusted=True, verdict=None):
    lines = [MARKER, "## Skill submission checks", "", "| Skill | Check | Result |", "| --- | --- | --- |"]
    if not trusted:
        from tools.ci.review_guard import WARNING

        lines[1] = "## Warning: " + WARNING
    if verdict is not None:
        status = "untrusted" if not trusted else "allowed" if verdict["allowed"] else "blocked"
        lines.extend(["", "Origin-computed execution gate: " + status + "."])
        for row in verdict["skills"]:
            lines.append("Gate branch for `" + row["skill"] + "`: " + row["branch"] + ".")
            lines.extend(row["warnings"])
    for result in results:
        skill = re.sub(r"[^A-Za-z0-9_/-]", "", str(result["skill"]))
        for name, check in result["checks"].items():
            name = re.sub(r"[^A-Za-z0-9_-]", "", name)
            status = check.get("status", "unknown")
            status = status if status in ("pass", "fail", "warning") else "unknown"
            if not trusted and status == "pass":
                status = "untrusted"
            lines.append(f"| `{skill}` | {name} | {status} |")
        signals = result.get("signals", {})
        lines.extend(
            [
                "",
                f"Quality signals for `{skill}`:",
                "",
                "```json",
                json.dumps(signals, sort_keys=True)[:2000].replace("```", ""),
                "```",
                "",
            ]
        )
        for name, check in result["checks"].items():
            if check.get("status") != "pass" and check.get("output"):
                # Keep untrusted output inside a code block and disable mentions.
                output = str(check["output"])[:3000].replace("```", "''' ").replace("@", "@\u200b")
                lines.extend(
                    [
                        f"<details><summary>{re.sub(r'[^A-Za-z0-9_-]', '', name)} details</summary>",
                        "",
                        "```text",
                        output,
                        "```",
                        "</details>",
                        "",
                    ]
                )
    return "\n".join(lines)[:60000]


def publish(repo, number, results, token, trusted=True, verdict=None):
    body = render(results, trusted, verdict)
    comments = pages(repo, f"issues/{number}/comments", token)
    sticky = next(
        (
            c
            for c in comments
            if c.get("user", {}).get("login") == "github-actions[bot]" and MARKER in c.get("body", "")
        ),
        None,
    )
    api(
        repo,
        f"issues/comments/{sticky['id']}" if sticky else f"issues/{number}/comments",
        token,
        "PATCH" if sticky else "POST",
        {"body": body},
    )
    if not trusted:
        return
    wanted = set().union(*(set(r.get("labels", [])) & LABELS for r in results))
    existing = pages(repo, "labels", token)
    for label in sorted(wanted - {v["name"] for v in existing}):
        api(repo, "labels", token, "POST", {"name": label, "color": "5319e7"})
    current = api(repo, f"issues/{number}", token)["labels"]
    # Replace only labels managed by this workflow, preserving human labels.
    kept = {v["name"] for v in current} - LABELS
    api(repo, f"issues/{number}/labels", token, "PUT", {"labels": sorted(kept | wanted)})


def apply_vendor_label(repo, number, verdict, token, untrusted=False):
    # Only origin-computed decisions can manage review labels.
    if not verdict["allowed"] or untrusted:
        label = "pending-security-review"
        if label not in {v["name"] for v in pages(repo, "labels", token)}:
            api(repo, "labels", token, "POST", {"name": label, "color": "b60205"})
        api(repo, f"issues/{number}/labels", token, "POST", {"labels": [label]})


def validate_submission_result(result):
    from tools.ci.emulator_report import text

    if not isinstance(result, dict) or set(result) != {"skill", "checks", "signals", "labels"}:
        raise ValueError("Invalid submission result schema")
    text(result["skill"], 180)
    if not re.fullmatch(r"skillhub/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", result["skill"]):
        raise ValueError("Invalid submission skill path")
    checks = result["checks"]
    if not isinstance(checks, dict) or set(checks) - {
        "ownership",
        "deleted",
        "version",
        "validate",
        "analyze",
        "lint",
        "test",
        "bandit",
        "semgrep",
    }:
        raise ValueError("Invalid submission checks")
    for check in checks.values():
        if (
            not isinstance(check, dict)
            or "status" not in check
            or set(check) - {"status", "output", "exit_code", "missing_subcommand"}
        ):
            raise ValueError("Invalid check schema")
        if check["status"] not in ("pass", "fail", "warning"):
            raise ValueError("Invalid check status")
        if "output" in check:
            output = check["output"]
            if not isinstance(output, str):
                raise ValueError("Invalid check output")
            text(output.replace("\n", " ").replace("\t", " "), 16000)
        if "exit_code" in check and (type(check["exit_code"]) is not int or not -255 <= check["exit_code"] <= 255):
            raise ValueError("Invalid exit code")
        if "missing_subcommand" in check and type(check["missing_subcommand"]) is not bool:
            raise ValueError("Invalid subcommand flag")
    signals = result["signals"]
    counts = {"fingerprints_verified", "validators", "validators_static", "validators_total", "bench_models"}
    nullable = {"tests_pass", "manifest_valid", "static_scan_clean"}
    allowed = (
        {"readme", "soft_md", "demo", "demo_all_actions", "before_after", "bench", "failure_modes", "last_verified"}
        | counts
        | nullable
    )
    if not isinstance(signals, dict) or set(signals) - allowed:
        raise ValueError("Invalid quality signal fields")
    for key, value in signals.items():
        if key in counts:
            if type(value) is not int or not 0 <= value <= 10000:
                raise ValueError("Invalid quality signal count")
        elif key == "last_verified":
            if value is not None:
                text(value, 64)
        elif type(value) is not bool and not (key in nullable and value is None):
            raise ValueError("Invalid quality signal value")
    labels = result["labels"]
    if (
        not isinstance(labels, list)
        or len(labels) > 10
        or any(not isinstance(label, str) or label not in LABELS for label in labels)
    ):
        raise ValueError("Invalid managed labels")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=int)
    args = parser.parse_args()
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    run = api(repo, f"actions/runs/{args.run}", token)
    if run["event"] != "pull_request":
        raise ValueError("Only pull request runs can be reported")
    pulls = run.get("pull_requests", [])
    if not pulls:
        # GitHub can omit fork PR associations from workflow_run payloads.
        pulls = [pr for pr in pages(repo, "pulls?state=open", token) if pr["head"]["sha"] == run["head_sha"]]
    if not pulls:
        print("No current associated PR; reporting skipped")
        return
    number = pulls[0]["number"]
    pr = api(repo, f"pulls/{number}", token)
    from tools.ci.review_guard import changed_files, modified_ci, remove_stale_approvals

    if pr["state"] == "open":
        remove_stale_approvals(repo, number, pr, token)
    if pr["head"]["sha"] != run["head_sha"] or pr["state"] != "open":
        print("Stale or closed PR; reporting skipped")
        return
    import yaml

    from tools.ci.trusted_vendor import origin_verdict

    try:
        files = changed_files(repo, number, pr, token)
        trusted = not modified_ci(files, run)
        verdict = origin_verdict(repo, pr, files, token, "skillhub/trusted-vendors.yml")
    except (OSError, ValueError, RuntimeError, yaml.YAMLError):
        trusted = False
        verdict = {"allowed": False, "skills": [], "approval_source": "none"}
    from tools.ci.emulator_report import artifact_list, bounded_json

    artifacts = artifact_list(repo, args.run, token) if trusted else []
    results = []
    for artifact in artifacts:
        if not re.fullmatch(r"skill-result-\d+", artifact["name"]) or artifact["expired"]:
            continue
        if len(results) >= 100:
            raise ValueError("Too many submission summaries")
        results.append(validate_submission_result(bounded_json(repo, artifact, token)))
    apply_vendor_label(repo, number, verdict, token, untrusted=not trusted)
    publish(repo, number, sorted(results, key=lambda r: r["skill"]), token, trusted, verdict)


if __name__ == "__main__":
    main()
