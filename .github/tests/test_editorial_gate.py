import copy
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "editorial_gate", Path(__file__).parents[1] / "scripts" / "editorial_gate.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
NOW = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
HEAD, BASE, ORIGINAL, MERGE = (character * 40 for character in "abcd")
BOT_LOGIN, BOT_ID = "test-editorial[bot]", 1234


def directory():
    return {
        "schema_version": 1,
        "published_at": "2026-11-01T00:00:00Z",
        "top50": ["42"],
        "rising": {},
        "projects": [
            {
                "id": "42",
                "full_name": "example/project",
                "stars": 100,
                "limitations": ["Requires a model provider."],
                "source_urls": [
                    "https://github.com/example/project/blob/main/README.md",
                    "https://docs.example.com/guide",
                ],
                "reviewed_at": "2026-11-01T00:00:00Z",
            },
            {"id": "43", "stars": 200},
        ],
    }


def proposal():
    result = directory()
    result["projects"][0]["limitations"].append("Upstream reports maintenance has ended.")
    result["projects"][0]["reviewed_at"] = "2026-11-23T10:00:00Z"
    return result


def pull_request():
    return {
        "number": 7,
        "state": "open",
        "merged": False,
        "draft": False,
        "mergeable": True,
        "merge_commit_sha": MERGE,
        "labels": [{"name": gate.LABEL}],
        "user": {"login": BOT_LOGIN, "id": BOT_ID, "type": "Bot"},
        "head": {
            "ref": "engine-editorial/2026-11-23-42",
            "sha": HEAD,
            "repo": {"full_name": gate.REPOSITORY},
        },
        "base": {"ref": "main", "repo": {"full_name": gate.REPOSITORY}},
    }


def review(state="APPROVED", head=HEAD, login="vikasrajput", review_id=1):
    return {
        "id": review_id,
        "state": state,
        "commit_id": head,
        "user": {"login": login, "type": "User"},
    }


class ProposalTests(unittest.TestCase):
    def test_accepts_single_limitation_with_dated_primary_source(self):
        actual = gate.validate_proposal(directory(), proposal(), "42", NOW)
        self.assertEqual(actual["id"], "42")

    def test_briefs_accept_sources_but_not_full_only_limitations(self):
        before, after = directory(), proposal()
        before["projects"][0].update(profile_kind="brief", limitations=[])
        after["projects"][0].update(profile_kind="brief")
        with self.assertRaises(gate.InvalidProposal):
            gate.validate_proposal(before, after, "42", NOW)
        after["projects"][0]["limitations"] = []
        after["projects"][0]["source_urls"].append(
            "https://github.com/example/project/releases/tag/v2"
        )
        gate.validate_proposal(before, after, "42", NOW)

    def test_forbidden_changes_and_type_substitutions(self):
        mutations = {
            "root ranking": lambda value: value["top50"].append("43"),
            "root timestamp": lambda value: value.update(published_at="2026-11-23T00:00:00Z"),
            "schema boolean": lambda value: value.update(schema_version=True),
            "second project": lambda value: value["projects"][1].update(stars=201),
            "metadata": lambda value: value["projects"][0].update(stars=101),
            "equal float metadata": lambda value: value["projects"][0].update(stars=100.0),
            "new project field": lambda value: value["projects"][0].update(intro="new"),
            "removed project": lambda value: value["projects"].pop(),
            "reordered projects": lambda value: value["projects"].reverse(),
            "date only": lambda value: value["projects"][0].update(
                limitations=directory()["projects"][0]["limitations"]
            ),
            "missing review update": lambda value: value["projects"][0].update(
                reviewed_at="2026-11-01T00:00:00Z"
            ),
            "future review": lambda value: value["projects"][0].update(
                reviewed_at="2026-12-01T00:00:00Z"
            ),
            "naive review": lambda value: value["projects"][0].update(reviewed_at="2026-11-23"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                value = proposal()
                mutate(value)
                with self.assertRaises(gate.InvalidProposal):
                    gate.validate_proposal(directory(), value, "42", NOW)

    def test_branch_id_must_identify_the_changed_project(self):
        with self.assertRaises(gate.InvalidProposal):
            gate.validate_proposal(directory(), proposal(), "43", NOW)

    def test_sources_only_and_not_reorder_only(self):
        value = directory()
        value["projects"][0]["source_urls"].append(
            "https://github.com/EXAMPLE/PROJECT/releases/tag/v2.0"
        )
        value["projects"][0]["reviewed_at"] = "2026-11-23T10:00:00Z"
        gate.validate_proposal(directory(), value, "42", NOW)
        value["projects"][0]["source_urls"] = list(
            reversed(directory()["projects"][0]["source_urls"])
        )
        with self.assertRaises(gate.InvalidProposal):
            gate.validate_proposal(directory(), value, "42", NOW)

    def test_new_source_must_be_https_and_canonical_primary(self):
        invalid = [
            "http://github.com/example/project/blob/main/README.md",
            "https://github.com/other/project/blob/main/README.md",
            "https://github.com/example/project.evil/blob/main/README.md",
            "https://github.com@example.org/example/project/blob/main/README.md",
            "https://github.com/example/project/blob/main/code.py",
            "https://github.com/example/project/issues/1",
            "https://github.com/example/project/blob/main/../README.md",
            "https://github.com/example/project/blob/main/%52EADME.md",
            "https://docs.example.com/new-unverified-source",
            "https://github.com/example/project/blob/main/README.md?redirect=evil",
            "https://github.com/example/project/blob/main/README.md\n",
            "https://[invalid",
        ]
        for url in invalid:
            with self.subTest(url=url):
                value = proposal()
                value["projects"][0]["source_urls"].append(url)
                with self.assertRaises(gate.InvalidProposal):
                    gate.validate_proposal(directory(), value, "42", NOW)

    def test_accepts_primary_readme_license_and_release_variants(self):
        for path in (
            "blob/main/README.md",
            "blob/v1/docs/README.rst#maintenance",
            "blob/main/LICENSE_EE.md",
            "blob/main/COPYING",
            "releases",
            "releases/tag/v1.0",
        ):
            with self.subTest(path=path):
                self.assertTrue(gate.primary_source("https://github.com/example/project/" + path, "Example/Project"))

    def test_weekly_metrics_can_move_but_editorial_baseline_cannot(self):
        original, current = directory(), directory()
        current["projects"][0]["stars"] = 123
        current["published_at"] = "2026-11-23T00:00:00Z"
        current["top50"] = ["43", "42"]
        gate.validate_current_base(original, current, proposal()["projects"][0])
        current["projects"][0]["limitations"].append("Another approved correction.")
        with self.assertRaises(gate.InvalidProposal):
            gate.validate_current_base(original, current, proposal()["projects"][0])

    def test_rejects_duplicate_json_and_nonfinite_numbers(self):
        for raw in (b'{"projects":[],"projects":[]}', b'{"value":NaN}', b'{"value":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(gate.InvalidProposal):
                gate.parse_directory(raw)


class IdentityAndApprovalTests(unittest.TestCase):
    def test_exact_bot_same_repo_branch_label_and_base(self):
        self.assertEqual(gate.eligible(pull_request(), BOT_LOGIN, BOT_ID), "42")
        for field, value in (("id", 999), ("login", "fake[bot]"), ("type", "User")):
            pr = pull_request()
            pr["user"][field] = value
            self.assertIsNone(gate.eligible(pr, BOT_LOGIN, BOT_ID))
        for key in ("head", "base"):
            pr = pull_request()
            pr[key]["repo"]["full_name"] = "attacker/fork"
            with self.assertRaises(gate.InvalidProposal):
                gate.eligible(pr, BOT_LOGIN, BOT_ID)
        pr = pull_request()
        pr["labels"] = []
        self.assertIsNone(gate.eligible(pr, BOT_LOGIN, BOT_ID))
        pr = pull_request()
        pr["head"]["ref"] = "engine-editorial/2026-02-31-42"
        with self.assertRaises(gate.InvalidProposal):
            gate.eligible(pr, BOT_LOGIN, BOT_ID)

    def test_only_real_owner_approval_on_current_head_counts(self):
        self.assertTrue(gate.approved([review(), review("COMMENTED", review_id=2)], HEAD))
        for reviews in (
            [],
            [review(login=BOT_LOGIN)],
            [review(head=BASE)],
            [review(), review("CHANGES_REQUESTED", review_id=2)],
            [review(), review("DISMISSED", review_id=2)],
        ):
            with self.subTest(reviews=reviews):
                self.assertFalse(gate.approved(reviews, HEAD))
        spoof = review()
        spoof["user"]["type"] = "Bot"
        self.assertFalse(gate.approved([spoof], HEAD))

    def test_all_other_checks_and_statuses_must_succeed(self):
        own = {"id": 1, "status": "in_progress"}
        external = {"id": 2, "status": "completed", "conclusion": "success"}
        self.assertTrue(gate.checks_successful([own, external], [{"state": "success"}], 1))
        for conclusion in ("neutral", "skipped", "failure", None):
            external["conclusion"] = conclusion
            self.assertFalse(gate.checks_successful([own, external], [], 1))
        self.assertFalse(gate.checks_successful([own], [{"state": "pending"}], 1))


class FakeGitHub:
    def __init__(self):
        self.pr = pull_request()
        self.fresh = None
        self.main = BASE
        self.original = directory()
        self.current = directory()
        self.proposal = proposal()
        self.merged = proposal()
        self.reviews = [review()]
        self.files = [{"filename": gate.DATA_PATH, "status": "modified"}]
        self.parents = [BASE, HEAD]
        self.checks = [{
            "id": 1, "head_sha": HEAD, "app": {"id": gate.ACTIONS_APP_ID},
            "status": "completed", "conclusion": "success",
        }]
        self.statuses = []
        self.calls = []
        self.check_results = []
        self.pr_reads = 0

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "PUT":
            return {"merged": True, "sha": "e" * 40}
        if path == "/pulls/7":
            self.pr_reads += 1
            return copy.deepcopy(self.fresh if self.fresh and self.pr_reads > 1 else self.pr)
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path == f"/compare/{BASE}...{HEAD}":
            return {"merge_base_commit": {"sha": ORIGINAL}}
        if path == f"/git/commits/{MERGE}":
            return {"parents": [{"sha": value} for value in self.parents]}
        raise AssertionError((method, path))

    def items(self, path, key=None):
        if path.endswith("/files"):
            return self.files
        if path.endswith("/reviews"):
            return self.reviews
        if "check-runs" in path:
            return self.checks
        if path.endswith("/status"):
            return self.statuses
        raise AssertionError(path)

    def directory(self, ref):
        return copy.deepcopy({
            ORIGINAL: self.original, HEAD: self.proposal, BASE: self.current, MERGE: self.merged,
        }[ref])

    def check(self, head, run_id):
        assert head == HEAD
        return 1

    def finish_check(self, check_id, conclusion, summary):
        self.check_results.append(conclusion)

    def merges(self):
        return [call for call in self.calls if call[0] == "PUT"]


class MergeFlowTests(unittest.TestCase):
    def run_gate(self, api):
        gate.process(api, 7, BOT_LOGIN, BOT_ID, "99", NOW)

    def test_merges_approved_exact_head_without_touching_weekly_metrics(self):
        api = FakeGitHub()
        api.current["projects"][0]["stars"] = 500
        api.merged["projects"][0]["stars"] = 500
        self.run_gate(api)
        self.assertEqual(len(api.merges()), 1)
        self.assertEqual(api.merges()[0][2]["sha"], HEAD)
        self.assertEqual(api.merges()[0][2]["merge_method"], "squash")
        self.assertEqual(api.check_results, ["success"])

    def test_unapproved_or_pending_checks_never_merge(self):
        for scenario in ("unapproved", "draft", "failing", "pending", "no test merge", "stale merge"):
            with self.subTest(scenario=scenario):
                api = FakeGitHub()
                if scenario == "unapproved":
                    api.reviews = []
                elif scenario == "draft":
                    api.pr["draft"] = True
                elif scenario == "failing":
                    api.checks.append({"id": 2, "status": "completed", "conclusion": "failure"})
                elif scenario == "pending":
                    api.statuses = [{"state": "pending"}]
                elif scenario == "no test merge":
                    api.pr["mergeable"] = None
                else:
                    api.parents = [ORIGINAL, HEAD]
                self.run_gate(api)
                self.assertEqual(api.merges(), [])

    def test_different_file_invalid_source_and_synthetic_extra_edit_fail(self):
        for scenario in ("file", "source", "extra merged edit", "stale editorial", "missing check"):
            with self.subTest(scenario=scenario):
                api = FakeGitHub()
                if scenario == "file":
                    api.files.append({"filename": ".github/workflows/evil.yml", "status": "added"})
                elif scenario == "source":
                    api.proposal["projects"][0]["source_urls"].append("https://evil.example/README")
                elif scenario == "extra merged edit":
                    api.merged["projects"][1]["stars"] = 900
                elif scenario == "stale editorial":
                    api.current["projects"][0]["limitations"].append("Changed independently.")
                else:
                    api.checks = []
                with self.assertRaises(gate.InvalidProposal):
                    self.run_gate(api)
                self.assertEqual(api.merges(), [])

    def test_head_or_label_changed_after_validation_never_merges(self):
        for scenario in ("head", "label"):
            with self.subTest(scenario=scenario):
                api = FakeGitHub()
                api.fresh = pull_request()
                if scenario == "head":
                    api.fresh["head"]["sha"] = ORIGINAL
                else:
                    api.fresh["labels"] = []
                self.run_gate(api)
                self.assertEqual(api.merges(), [])

    def test_approval_or_base_changed_at_final_recheck_never_merges(self):
        for scenario in ("base", "approval"):
            with self.subTest(scenario=scenario):
                api = FakeGitHub()
                original_request = api.request
                original_items = api.items
                reads = {"base": 0, "approval": 0}

                def request(method, path, payload=None):
                    if path == "/git/ref/heads/main":
                        reads["base"] += 1
                        if scenario == "base" and reads["base"] > 1:
                            return {"object": {"sha": ORIGINAL}}
                    return original_request(method, path, payload)

                def items(path, key=None):
                    if path.endswith("/reviews"):
                        reads["approval"] += 1
                        if scenario == "approval" and reads["approval"] > 1:
                            return [review("DISMISSED")]
                    return original_items(path, key)

                api.request, api.items = request, items
                self.run_gate(api)
                self.assertEqual(api.merges(), [])

    def test_missing_identity_disables_merging_without_network_calls(self):
        with patch.dict(gate.os.environ, {
            "GITHUB_REPOSITORY": gate.REPOSITORY,
            "EDITORIAL_BOT_LOGIN": "",
            "EDITORIAL_BOT_ID": "",
        }, clear=True), patch.object(gate, "GitHub") as api:
            gate.main()
            api.assert_not_called()

    def test_check_creation_rejects_an_untrusted_issuer(self):
        api = gate.GitHub("not-a-real-token")
        for value in (
            {"id": 1, "head_sha": HEAD, "app": {"id": 99, "slug": "github-actions"}},
            {"id": 1, "head_sha": BASE, "app": {"id": gate.ACTIONS_APP_ID, "slug": "github-actions"}},
        ):
            with self.subTest(value=value), patch.object(api, "request", return_value=value):
                with self.assertRaises(gate.InvalidProposal):
                    api.check(HEAD, "99")


if __name__ == "__main__":
    unittest.main()
