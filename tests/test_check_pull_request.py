# SPDX-License-Identifier: AGPL-3.0-only

import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-pull-request.py"
CHECK = runpy.run_path(str(SCRIPT))["main"]


class PullRequestTests(unittest.TestCase):
    def run_check(self, changes, body="", before=(), after=()):
        event = {"pull_request": {"base": {"sha": "target"}, "head": {"sha": "proposal"}, "body": body}}
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps(event))
            git = Mock(side_effect=["ancestor\n", changes])
            images_at = Mock(side_effect=[set(after), set(before)])
            check_image = Mock()
            with (
                patch.object(sys, "argv", [str(SCRIPT), str(event_path)]),
                patch.dict(CHECK.__globals__, git=git, images_at=images_at, check_image=check_image),
            ):
                CHECK()
            git.assert_called_with("diff", "--no-renames", "--name-status", "-z", "ancestor", "proposal", "--")
            return check_image.call_args_list

    def test_rejects_changes_to_two_apps_including_deletions(self):
        with self.assertRaisesRegex(ValueError, "alpha, beta"):
            self.run_check("D\0apps/alpha/icon.svg\0A\0apps/beta/icon.svg\0")

    def test_infrastructure_and_non_image_changes_need_no_links(self):
        calls = self.run_check("M\0apps/alpha/nex.yaml\0M\0.github/workflows/validate.yml\0",
                               before=["demo:latest"], after=["demo:latest"])
        self.assertEqual(calls, [])

    def test_icon_replacement_requires_an_official_source_link(self):
        with self.assertRaisesRegex(ValueError, "Official app icon source"):
            self.run_check("D\0apps/alpha/icon.svg\0A\0apps/alpha/icon.png\0")
        self.run_check("A\0apps/alpha/icon.png\0", "Official app icon source: https://example.org/logo.png")

    def test_checks_only_added_image_references(self):
        with self.assertRaisesRegex(ValueError, "Container image source"):
            self.run_check("M\0apps/alpha/nex.yaml\0", before=["demo:latest"], after=["demo:v2"])
        calls = self.run_check("M\0apps/alpha/nex.yaml\0",
                               "Container image source: [Upstream](https://example.org/container)",
                               before=["shared:latest", "demo:latest"], after=["shared:latest", "demo:v2"])
        self.assertEqual(calls, [call("demo:v2")])
