from collections import Counter
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


SPEC = importlib.util.spec_from_file_location(
    "profile_stats", Path(__file__).resolve().parents[1] / "scripts" / "profile_stats.py"
)
cards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cards)


def repository(size, fork=False, more_languages=False):
    return {
        "isFork": fork,
        "stargazerCount": 2,
        "languages": {
            "pageInfo": {"hasNextPage": more_languages},
            "edges": [{"size": size, "node": {"name": "Python", "color": "#3572A5"}}],
        },
    }


def summary(login="freeloadsk"):
    return {
        "viewer": {"login": login},
        "user": {"contributionsCollection": {
            "totalCommitContributions": 11,
            "totalPullRequestContributions": 3,
            "totalIssueContributions": 2,
            "totalPullRequestReviewContributions": 4,
        }},
    }


def page(repositories, cursor=None):
    return {"user": {"repositories": {
        "nodes": repositories,
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
    }}}


class ProfileStatsTests(unittest.TestCase):
    def test_pagination_combines_all_repositories_and_excludes_forks_from_languages(self):
        calls = []
        responses = iter([
            summary(),
            page([repository(100), repository(99999, fork=True)], "next-page"),
            page([repository(300)]),
        ])

        def request(token, query, variables):
            calls.append(variables)
            return next(responses)

        stats, sizes, colors = cards.collect(
            "freeloadsk", "test-token", datetime(2026, 11, 7, tzinfo=timezone.utc), request
        )
        self.assertNotIn("Repositories", stats)
        self.assertEqual(stats["Stars earned"], 4)
        self.assertEqual(stats["Commits (365 days)"], 11)
        self.assertEqual(sizes, {"Python": 400})
        self.assertEqual(colors, {"Python": "#3572A5"})
        self.assertEqual(calls[2]["cursor"], "next-page")
        self.assertEqual(calls[0]["from"], "2025-11-07T00:00:00+00:00")

    def test_rejects_token_for_another_account(self):
        with self.assertRaisesRegex(RuntimeError, "profile owner"):
            cards.collect("freeloadsk", "test-token", request=lambda *args: summary("other"))

    def test_refuses_incomplete_languages(self):
        responses = iter([summary(), page([repository(100, more_languages=True)])])
        with self.assertRaisesRegex(RuntimeError, "incomplete totals"):
            cards.collect("freeloadsk", "test-token", request=lambda *args: next(responses))

    def test_rejects_repeated_pagination_cursor(self):
        responses = iter([summary(), page([], "same"), page([], "same")])
        with self.assertRaisesRegex(RuntimeError, "pagination cursor"):
            cards.collect("freeloadsk", "test-token", request=lambda *args: next(responses))

    def test_graphql_error_does_not_expose_response_details(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"errors":[{"message":"sensitive-repository-name"}],"data":{}}'

        with patch.object(cards, "urlopen", return_value=Response()):
            with self.assertRaises(RuntimeError) as context:
                cards.graphql("secret-token", "query {}", {})
        self.assertNotIn("sensitive-repository-name", str(context.exception))
        self.assertNotIn("secret-token", str(context.exception))

    def test_svg_escapes_text_and_uses_full_denominator(self):
        sizes = Counter({f"Language {i}": 10 for i in range(7)})
        sizes['A&B <script>'] = 30
        svg = cards.languages_card(sizes, {'A&B <script>': '" onload="bad'})
        root = ET.fromstring(svg)
        text = " ".join(root.itertext())
        self.assertIn("30.0%", text)
        self.assertIn("A&B <script>", text)
        self.assertNotIn("onload", svg)
        ET.fromstring(cards.stats_card("A&B", {"Commits": 1234}))

    def test_empty_languages_produce_valid_svg(self):
        root = ET.fromstring(cards.languages_card(Counter(), {}))
        self.assertIn("No language data", " ".join(root.itertext()))

    def test_publish_preserves_readme_outside_markers_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "README.md"
            before = "# Hello 👋\r\n\r\n" + cards.START + "\r\nold cards\r\n" + cards.END + "\r\nKeep me.\r\n"
            readme.write_bytes(before.encode())
            cards.publish(root, "freeloadsk", {"Stars earned": 1}, Counter(Python=10), {})
            after = readme.read_bytes()
            self.assertTrue(after.startswith(("# Hello 👋\r\n\r\n" + cards.START).encode()))
            self.assertTrue(after.endswith((cards.END + "\r\nKeep me.\r\n").encode()))
            self.assertIn(b"./profile/stats.svg", after)
            self.assertNotIn(b"old cards", after)
            for path in (root / "profile").glob("*.svg"):
                ET.parse(path)
            cards.publish(root, "freeloadsk", {"Stars earned": 1}, Counter(Python=10), {})
            self.assertEqual(readme.read_bytes(), after)

    def test_bad_markers_do_not_overwrite_existing_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Unmarked README", encoding="utf-8")
            (root / "profile").mkdir()
            old = root / "profile" / "stats.svg"
            old.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "marker pair"):
                cards.publish(root, "freeloadsk", {}, Counter(), {})
            self.assertEqual(old.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
