"""Validate narrowly scoped editorial PRs; never execute proposal code."""

import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


REPOSITORY = "vikasrajput/top-ai-agents"
DATA_PATH = "data/directory.json"
LABEL = "engine-editorial"
CHECK_NAME = "Editorial proposal validation"
ACTIONS_APP_ID = 15368
FIELDS = {"limitations", "source_urls", "reviewed_at"}
BRANCH = re.compile(r"engine-editorial/(\d{4}-\d{2}-\d{2})-([1-9]\d*)")
SHA = re.compile(r"[0-9a-f]{40}")


class InvalidProposal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidProposal(message)


def same(left, right):
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def timestamp(value):
    require(isinstance(value, str), "reviewed_at must be a timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidProposal("Invalid reviewed_at timestamp.") from error
    require(parsed.tzinfo is not None, "reviewed_at must include a timezone.")
    return parsed


def strings(value, field, allow_empty=False):
    require(
        isinstance(value, list)
        and (allow_empty or value)
        and all(
            isinstance(item, str) and item.strip() and item == item.strip()
            for item in value
        ),
        f"{field} must be an array of nonempty, trimmed strings.",
    )
    require(len(value) == len(set(value)), f"{field} must not contain duplicates.")


def primary_source(url, full_name):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.query
        or "%" in parsed.path
        or "\\" in url
    ):
        return False
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 3 or "/".join(parts[:2]).casefold() != full_name.casefold():
        return False
    if any(part in (".", "..") for part in parts):
        return False
    if parts[2] == "releases":
        return len(parts) == 3 or (
            len(parts) >= 5 and parts[3] == "tag" and all(parts[4:])
        )
    return (
        len(parts) >= 5
        and parts[2] == "blob"
        and all(parts[3:])
        and re.fullmatch(
            r"(?:readme|licen[cs]e|copying)(?:[._-][a-z0-9._-]+)?",
            parts[-1],
            re.IGNORECASE,
        )
        is not None
    )


def validate_proposal(before, after, project_id, now):
    require(isinstance(before, dict) and isinstance(after, dict), "Invalid directory object.")
    require(
        type(before.get("schema_version")) is type(after.get("schema_version")) is int
        and before["schema_version"] == after["schema_version"] == 1,
        "Expected schema v1.",
    )
    projects_before = before.get("projects")
    projects_after = after.get("projects")
    require(
        isinstance(projects_before, list)
        and isinstance(projects_after, list)
        and len(projects_before) == len(projects_after),
        "Projects cannot be added or removed.",
    )
    require(
        same(
            {key: value for key, value in before.items() if key != "projects"},
            {key: value for key, value in after.items() if key != "projects"},
        ),
        "Root values, rankings and metrics cannot change.",
    )
    ids = [project.get("id") for project in projects_before if isinstance(project, dict)]
    require(
        len(ids) == len(projects_before)
        and all(isinstance(value, str) for value in ids)
        and len(set(ids)) == len(ids),
        "Invalid project identities.",
    )
    changed = [
        (old, new)
        for old, new in zip(projects_before, projects_after)
        if not same(old, new)
    ]
    require(len(changed) == 1, "Exactly one project must change.")
    old, new = changed[0]
    require(isinstance(new, dict), "Invalid updated project.")
    require(old["id"] == new.get("id") == project_id, "Branch and project identities must match.")
    require(set(old) == set(new), "Project fields cannot be added or removed.")
    differences = {key for key in old if not same(old[key], new[key])}
    require(differences <= FIELDS, "Only limitations, source_urls and reviewed_at may change.")
    require(bool(differences - {"reviewed_at"}), "Date-only edits are not proposals.")
    require("reviewed_at" in differences, "Editorial changes require a fresh reviewed_at.")
    strings(new.get("limitations"), "limitations", allow_empty=True)
    strings(new.get("source_urls"), "source_urls")
    require(
        new.get("profile_kind") != "brief" or new["limitations"] == [],
        "Brief profiles cannot gain full-only limitations.",
    )
    require(
        any(set(old[field]) != set(new[field]) for field in ("limitations", "source_urls")),
        "Reordering existing text or sources is not a substantive proposal.",
    )
    require(
        timestamp(old.get("reviewed_at")) < timestamp(new["reviewed_at"]) <= now + timedelta(minutes=5),
        "reviewed_at must advance and cannot be in the future.",
    )
    for url in new["source_urls"]:
        try:
            parsed = urlsplit(url)
        except ValueError as error:
            raise InvalidProposal("Invalid source URL.") from error
        require(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and "\\" not in url
            and not any(character.isspace() for character in url),
            "Sources must be HTTPS URLs without credentials or whitespace.",
        )
        require(
            url in old["source_urls"] or primary_source(url, old["full_name"]),
            "New sources must be this project's primary GitHub README, license or release.",
        )
    require(
        any(primary_source(url, old["full_name"]) for url in new["source_urls"]),
        "At least one primary GitHub source for this project is required.",
    )
    return new


def validate_current_base(original, current, proposed):
    original_by_id = {project["id"]: project for project in original["projects"]}
    current_by_id = {project["id"]: project for project in current["projects"]}
    previous = original_by_id[proposed["id"]]
    present = current_by_id.get(proposed["id"])
    require(present is not None, "Project no longer exists on main.")
    require(
        present["full_name"] == previous["full_name"]
        and all(same(present.get(field), previous.get(field)) for field in FIELDS),
        "Editorial baseline changed; refresh the proposal and obtain a new review.",
    )


def approved(reviews, head):
    decisions = [
        review
        for review in reviews
        if review.get("user", {}).get("login", "").casefold() == "vikasrajput"
        and review.get("user", {}).get("type") == "User"
        and review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
    ]
    if not decisions:
        return False
    latest = max(decisions, key=lambda review: review["id"])
    return latest["state"] == "APPROVED" and latest.get("commit_id") == head


def eligible(pr, bot_login, bot_id):
    match = BRANCH.fullmatch(pr.get("head", {}).get("ref", ""))
    if (
        not match
        or LABEL not in {label["name"] for label in pr.get("labels", [])}
        or pr.get("user", {}).get("login") != bot_login
        or pr.get("user", {}).get("id") != bot_id
        or pr.get("user", {}).get("type") != "Bot"
    ):
        return None
    try:
        datetime.strptime(match[1], "%Y-%m-%d")
    except ValueError as error:
        raise InvalidProposal("Invalid branch date.") from error
    require(pr.get("state") == "open" and not pr.get("merged"), "PR must be open.")
    require(pr["base"]["ref"] == "main", "PR must target main.")
    require(
        pr["head"].get("repo", {}).get("full_name") == REPOSITORY
        and pr["base"].get("repo", {}).get("full_name") == REPOSITORY,
        "Only same-repository proposals are allowed.",
    )
    require(SHA.fullmatch(pr["head"]["sha"]) is not None, "Invalid PR head SHA.")
    return match[2]


def checks_successful(checks, statuses, validation_id):
    return all(
        check["id"] == validation_id
        or (check["status"] == "completed" and check.get("conclusion") == "success")
        for check in checks
    ) and all(status.get("state") == "success" for status in statuses)


def parse_directory(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON object key.")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise InvalidProposal("Nonfinite JSON number.")

    require(len(raw) <= 2_000_000, "Directory exceeds the editorial validation size limit.")
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidProposal("Invalid directory JSON.") from error


class GitHub:
    def __init__(self, token):
        self.token = token
        self.root = f"/repos/{REPOSITORY}"

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            "https://api.github.com" + self.root + path,
            data=body,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"GitHub {method} {path.split('?')[0]} returned HTTP {error.code}.") from error

    def items(self, path, key=None):
        result = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            payload = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            batch = payload[key] if key else payload
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise RuntimeError("GitHub pagination limit exceeded.")

    def directory(self, ref):
        require(SHA.fullmatch(ref) is not None, "Contents require an immutable SHA.")
        file = self.request("GET", f"/contents/{DATA_PATH}?ref={quote(ref, safe='')}")
        require(file.get("encoding") == "base64" and file.get("type") == "file", "Expected JSON file.")
        return parse_directory(base64.b64decode(file["content"], validate=False))

    def check(self, head, run_id):
        result = self.request("POST", "/check-runs", {
            "name": CHECK_NAME,
            "head_sha": head,
            "status": "in_progress",
            "external_id": run_id,
            "details_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
        })
        require(
            result.get("app", {}).get("id") == ACTIONS_APP_ID
            and result.get("app", {}).get("slug") == "github-actions"
            and result.get("head_sha") == head,
            "Validation check must be issued by GitHub Actions for this head.",
        )
        return result["id"]

    def finish_check(self, check_id, conclusion, summary):
        self.request("PATCH", f"/check-runs/{check_id}", {
            "status": "completed",
            "conclusion": conclusion,
            "output": {"title": CHECK_NAME, "summary": summary},
        })


def process(api, number, bot_login, bot_id, run_id, now):
    pr = api.request("GET", f"/pulls/{number}")
    project_id = eligible(pr, bot_login, bot_id)
    if project_id is None:
        print(f"PR #{number}: not a configured editorial proposal; ignored.")
        return
    head = pr["head"]["sha"]
    check_id = api.check(head, run_id)
    try:
        files = api.items(f"/pulls/{number}/files")
        require(
            len(files) == 1
            and files[0].get("filename") == DATA_PATH
            and files[0].get("status") == "modified"
            and "previous_filename" not in files[0],
            "Proposal must modify only data/directory.json.",
        )
        main = api.request("GET", "/git/ref/heads/main")["object"]["sha"]
        comparison = api.request("GET", f"/compare/{main}...{head}")
        original = api.directory(comparison["merge_base_commit"]["sha"])
        proposal = api.directory(head)
        updated = validate_proposal(original, proposal, project_id, now)
        current = api.directory(main)
        validate_current_base(original, current, updated)
    except InvalidProposal as error:
        api.finish_check(check_id, "failure", str(error))
        raise
    api.finish_check(check_id, "success", "One project's editorial fields validated against primary-source URL rules.")
    if pr.get("draft") or not approved(api.items(f"/pulls/{number}/reviews"), head):
        print(f"PR #{number}: validated; awaiting vikasrajput approval on the current head.")
        return
    if not pr.get("mergeable") or not pr.get("merge_commit_sha"):
        print(f"PR #{number}: awaiting a clean GitHub test merge.")
        return
    test_merge = api.request("GET", f"/git/commits/{pr['merge_commit_sha']}")
    if [parent["sha"] for parent in test_merge["parents"]] != [main, head]:
        print(f"PR #{number}: test merge is stale; waiting for GitHub to refresh it.")
        return
    try:
        merged = api.directory(pr["merge_commit_sha"])
        verified = validate_proposal(current, merged, project_id, now)
        require(
            all(same(verified[field], updated[field]) for field in FIELDS),
            "Test merge differs from the approved editorial payload.",
        )
    except InvalidProposal as error:
        api.finish_check(check_id, "failure", str(error))
        raise
    checks = api.items(f"/commits/{head}/check-runs?filter=latest", "check_runs")
    statuses = api.items(f"/commits/{head}/status", "statuses")
    require(
        any(
            check["id"] == check_id
            and check.get("app", {}).get("id") == ACTIONS_APP_ID
            and check.get("head_sha") == head
            and check.get("status") == "completed"
            and check.get("conclusion") == "success"
            for check in checks
        ),
        "Successful current-head validation check is missing.",
    )
    if not checks_successful(checks, statuses, check_id):
        print(f"PR #{number}: waiting for all current-head checks and statuses to succeed.")
        return
    fresh = api.request("GET", f"/pulls/{number}")
    if (
        eligible(fresh, bot_login, bot_id) != project_id
        or fresh["head"]["sha"] != head
        or fresh.get("draft")
        or api.request("GET", "/git/ref/heads/main")["object"]["sha"] != main
        or not approved(api.items(f"/pulls/{number}/reviews"), head)
    ):
        print(f"PR #{number}: approval, head or base changed; no merge attempted.")
        return
    result = api.request("PUT", f"/pulls/{number}/merge", {
        "sha": head,
        "merge_method": "squash",
        "commit_title": f"Apply reviewed editorial update for project {project_id}",
        "commit_message": f"Approved editorial update via PR #{number}.",
    })
    require(result.get("merged") is True, "GitHub did not merge the approved proposal.")
    print(f"PR #{number}: merged approved editorial update at {result['sha']}.")


def main():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Unexpected workflow repository.")
    login = os.environ.get("EDITORIAL_BOT_LOGIN", "")
    actor_id = os.environ.get("EDITORIAL_BOT_ID", "")
    if not login or not actor_id:
        print("::notice::Editorial merging is disabled: configure EDITORIAL_BOT_LOGIN and EDITORIAL_BOT_ID.")
        return
    require(login.endswith("[bot]") and actor_id.isdecimal(), "Invalid configured App identity.")
    api = GitHub(os.environ["GH_TOKEN"])
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        event = json.load(event_file)
    number = event.get("pull_request", {}).get("number") or event.get("inputs", {}).get("pr_number")
    if number:
        require(str(number).isdecimal() and int(number) > 0, "Invalid PR number.")
        numbers = [int(number)]
    else:
        numbers = [
            pr["number"] for pr in api.items("/pulls?state=open&base=main")
            if LABEL in {label["name"] for label in pr.get("labels", [])}
        ]
    failures = []
    for number in numbers:
        try:
            process(api, number, login, int(actor_id), os.environ["GITHUB_RUN_ID"], datetime.now(timezone.utc))
        except InvalidProposal as error:
            print(f"::error::PR #{number}: {error}")
            failures.append(number)
    require(not failures, f"Editorial proposals failed validation: {failures}")


if __name__ == "__main__":
    main()
