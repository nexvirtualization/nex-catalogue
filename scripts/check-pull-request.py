#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Check the scope, source links and new container images of a pull request."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import yaml


def git(*args):
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8", errors="surrogateescape")


def changed_app(base, head):
    entries = git("diff", "--no-renames", "--name-status", "-z", base, head, "--").split("\0")[:-1]
    changes = {}
    for status, name in zip(entries[::2], entries[1::2]):
        parts = PurePosixPath(name).parts
        if len(parts) >= 2 and parts[0] == "apps":
            changes.setdefault(parts[1], {})[parts[2:]] = status
    if len(changes) > 1:
        raise ValueError("A pull request can change at most one catalogue app. Changed apps: " + ", ".join(sorted(changes)))
    return next(iter(changes.items()), (None, {}))


def images_at(commit, manifest):
    if not git("ls-tree", "--name-only", commit, "--", manifest).strip():
        return set()
    document = yaml.safe_load(git("show", f"{commit}:{manifest}"))
    return {service["image"] for service in document["services"].values()}


def has_source(body, label):
    for line in body.splitlines():
        if not line.strip().lower().startswith(label.lower() + ":"):
            continue
        for url in re.findall(r'https://[^\s<>()\]]+', line):
            parsed = urlsplit(url)
            if parsed.hostname and not parsed.username and not parsed.password:
                return True
    return False


def check_image(image):
    if not image.endswith(":latest"):
        print(f"Prefer :latest when upstream supports it. This PR uses {image}.", flush=True)
    for attempt in range(2):
        try:
            result = subprocess.run(
                ["docker", "manifest", "inspect", "--", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                return
            error = result.stderr.strip()
        except subprocess.TimeoutExpired:
            error = "Registry lookup timed out"
        if attempt == 0:
            time.sleep(2)
    raise ValueError(f"Could not resolve container image {image}: {error}")


def main():
    event = json.loads(Path(sys.argv[1]).read_text())["pull_request"]
    base = git("merge-base", event["base"]["sha"], event["head"]["sha"]).strip()
    head = event["head"]["sha"]
    app, changes = changed_app(base, head)
    if not app:
        return

    new_images = set()
    if changes.get(("nex.yaml",)) not in (None, "D"):
        manifest = f"apps/{app}/nex.yaml"
        new_images = images_at(head, manifest) - images_at(base, manifest)
    new_icon = any(changes.get((name,)) not in (None, "D") for name in ("icon.svg", "icon.png"))
    body = event.get("body") or ""
    required_sources = (
        (new_images, "Container image source"),
        (new_icon, "Official app icon source"),
    )
    for required, label in required_sources:
        if required and not has_source(body, label):
            raise ValueError(f"Add an HTTPS source link on the '{label}:' line of the pull request description.")

    for image in sorted(new_images):
        check_image(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        raise SystemExit(str(error)) from None
