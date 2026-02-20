"""Tests for contextcore manifest fix — resolve open questions in manifests."""

import json

import pytest
import yaml
from click.testing import CliRunner

from contextcore.cli.manifest import manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_V2_MANIFEST = {
    "apiVersion": "contextcore.io/v1alpha2",
    "kind": "ContextManifest",
    "metadata": {
        "name": "test-project",
        "owners": [{"team": "engineering"}],
        "changelog": [],
    },
    "spec": {
        "project": {
            "id": "test-project",
            "name": "Test Project",
        },
        "business": {
            "criticality": "medium",
            "owner": "engineering",
        },
        "targets": [
            {
                "kind": "Deployment",
                "name": "test-service",
                "namespace": "default",
            },
        ],
    },
    "strategy": {"objectives": [], "tactics": []},
    "guidance": {
        "constraints": [],
        "preferences": [],
        "questions": [],
    },
    "insights": [],
}


def _make_manifest(tmp_path, questions=None):
    """Create a v2 manifest with optional questions."""
    data = json.loads(json.dumps(MINIMAL_V2_MANIFEST))  # deep copy
    if questions:
        data["guidance"]["questions"] = questions
    path = tmp_path / ".contextcore.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return path


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def manifest_with_open_questions(tmp_path):
    """Manifest with 3 open questions."""
    questions = [
        {"id": "Q-001", "question": "What is the deployment target?", "status": "open", "priority": "high"},
        {"id": "Q-002", "question": "Which monitoring stack is used?", "status": "open", "priority": "medium"},
        {"id": "Q-003", "question": "What SLO target for availability?", "status": "open", "priority": "low"},
    ]
    return _make_manifest(tmp_path, questions)


@pytest.fixture
def manifest_no_questions(tmp_path):
    """Manifest with no open questions."""
    return _make_manifest(tmp_path)


@pytest.fixture
def manifest_already_answered(tmp_path):
    """Manifest where all questions are already answered."""
    questions = [
        {
            "id": "Q-001",
            "question": "What is the deployment target?",
            "status": "answered",
            "priority": "high",
            "answer": "Kubernetes",
            "answeredBy": "human",
        },
    ]
    return _make_manifest(tmp_path, questions)


@pytest.fixture
def answers_file(tmp_path):
    """YAML answers file matching Q-001 and Q-002 but not Q-003."""
    answers = {
        "Q-001": "Kubernetes on GKE",
        "Q-002": "Grafana Cloud (Mimir + Loki + Tempo)",
    }
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.dump(answers))
    return path


@pytest.fixture
def full_answers_file(tmp_path):
    """YAML answers file matching all 3 questions."""
    answers = {
        "Q-001": "Kubernetes on GKE",
        "Q-002": "Grafana Cloud (Mimir + Loki + Tempo)",
        "Q-003": "99.9% availability",
    }
    path = tmp_path / "full-answers.yaml"
    path.write_text(yaml.dump(answers))
    return path


# ---------------------------------------------------------------------------
# Tests: detection
# ---------------------------------------------------------------------------


class TestFixDetectsOpenQuestions:
    def test_detects_open_questions(self, runner, manifest_with_open_questions):
        """Report-only mode lists open questions."""
        result = runner.invoke(
            manifest, ["fix", "--path", str(manifest_with_open_questions)]
        )
        assert result.exit_code == 0, result.output
        assert "3 fixable issue(s)" in result.output
        assert "Q-001" in result.output

    def test_detects_open_questions_json(self, runner, manifest_with_open_questions):
        """JSON report-only mode returns structured output."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "-f", "json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "report_only"
        assert data["total_issues"] == 3
        assert len(data["open_questions"]) == 3


# ---------------------------------------------------------------------------
# Tests: answers file
# ---------------------------------------------------------------------------


class TestFixAnswersFileResolves:
    def test_answers_file_resolves_matching(self, runner, manifest_with_open_questions, answers_file):
        """Answers file resolves Q-001 and Q-002 but not Q-003."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(answers_file)],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 2 question(s)" in result.output

        # Verify manifest was updated
        updated = yaml.safe_load(manifest_with_open_questions.read_text())
        questions = updated["guidance"]["questions"]
        q1 = next(q for q in questions if q["id"] == "Q-001")
        assert q1["status"] == "answered"
        assert q1["answer"] == "Kubernetes on GKE"
        assert q1["answeredBy"] == "answers-file"

    def test_answers_file_partial_reports_unmatched(
        self, runner, manifest_with_open_questions, answers_file
    ):
        """Unmatched question IDs are reported."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(answers_file)],
        )
        assert "Unmatched" in result.output
        assert "Q-003" in result.output

    def test_answers_file_full_resolves_all(
        self, runner, manifest_with_open_questions, full_answers_file
    ):
        """Full answers file resolves all 3 questions."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(full_answers_file)],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 3 question(s)" in result.output

        updated = yaml.safe_load(manifest_with_open_questions.read_text())
        questions = updated["guidance"]["questions"]
        for q in questions:
            assert q["status"] == "answered"


# ---------------------------------------------------------------------------
# Tests: interactive
# ---------------------------------------------------------------------------


class TestFixInteractive:
    def test_interactive_resolves_questions(self, runner, manifest_with_open_questions):
        """Interactive mode prompts and resolves questions."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--interactive"],
            input="Kubernetes\nGrafana Cloud\n99.9%\n",
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 3 question(s)" in result.output

    def test_interactive_skip_empty_answer(self, runner, manifest_with_open_questions):
        """Empty answers in interactive mode are skipped."""
        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--interactive"],
            input="Kubernetes\n\n99.9%\n",
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 2 question(s)" in result.output


# ---------------------------------------------------------------------------
# Tests: dry run
# ---------------------------------------------------------------------------


class TestFixDryRun:
    def test_dry_run_does_not_write(self, runner, manifest_with_open_questions, full_answers_file):
        """Dry run reports fixes but does not modify the file."""
        original = manifest_with_open_questions.read_text()
        result = runner.invoke(
            manifest,
            [
                "fix",
                "--path", str(manifest_with_open_questions),
                "--answers", str(full_answers_file),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would fix 3 question(s)" in result.output
        # File unchanged
        assert manifest_with_open_questions.read_text() == original


# ---------------------------------------------------------------------------
# Tests: no issues
# ---------------------------------------------------------------------------


class TestFixNoIssues:
    def test_no_issues_exits_cleanly(self, runner, manifest_no_questions):
        """Manifest with no open questions exits with 'Nothing to fix'."""
        result = runner.invoke(
            manifest, ["fix", "--path", str(manifest_no_questions)]
        )
        assert result.exit_code == 0, result.output
        assert "Nothing to fix" in result.output

    def test_already_answered_exits_cleanly(self, runner, manifest_already_answered):
        """Manifest where all questions are already answered exits cleanly."""
        result = runner.invoke(
            manifest, ["fix", "--path", str(manifest_already_answered)]
        )
        assert result.exit_code == 0, result.output
        assert "Nothing to fix" in result.output


# ---------------------------------------------------------------------------
# Tests: status value correctness
# ---------------------------------------------------------------------------


class TestFixSetsAnsweredStatus:
    def test_status_is_answered_not_resolved(
        self, runner, manifest_with_open_questions, full_answers_file
    ):
        """Verify status='answered' (QuestionStatus.ANSWERED), not 'resolved'."""
        runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(full_answers_file)],
        )
        updated = yaml.safe_load(manifest_with_open_questions.read_text())
        questions = updated["guidance"]["questions"]
        for q in questions:
            assert q["status"] == "answered", (
                f"Question {q['id']} has status={q['status']!r}, expected 'answered'"
            )

    def test_json_output_shows_actions(
        self, runner, manifest_with_open_questions, full_answers_file
    ):
        """JSON output mode includes action details."""
        result = runner.invoke(
            manifest,
            [
                "fix",
                "--path", str(manifest_with_open_questions),
                "--answers", str(full_answers_file),
                "-f", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "applied"
        assert data["fixed"] == 3
        assert len(data["actions"]) == 3
        for action in data["actions"]:
            assert action["old_status"] == "open"
            assert action["action"] == "answered"


# ---------------------------------------------------------------------------
# Tests: answers file format variants
# ---------------------------------------------------------------------------


class TestAnswersFileFormats:
    def test_list_format_answers_file(self, runner, manifest_with_open_questions, tmp_path):
        """Answers file in list-of-dicts format."""
        answers = [
            {"id": "Q-001", "answer": "Kubernetes"},
            {"id": "Q-002", "answer": "Grafana Cloud"},
        ]
        path = tmp_path / "list-answers.yaml"
        path.write_text(yaml.dump(answers))

        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(path)],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 2 question(s)" in result.output

    def test_json_format_answers_file(self, runner, manifest_with_open_questions, tmp_path):
        """Answers file in JSON dict format."""
        answers = {"Q-001": "Kubernetes", "Q-003": "99.9%"}
        path = tmp_path / "answers.json"
        path.write_text(json.dumps(answers))

        result = runner.invoke(
            manifest,
            ["fix", "--path", str(manifest_with_open_questions), "--answers", str(path)],
        )
        assert result.exit_code == 0, result.output
        assert "Fixed 2 question(s)" in result.output
