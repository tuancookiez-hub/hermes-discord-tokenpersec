"""Check plugin-catalog-entry.yaml agrees with discord-tps/plugin.yaml and git.

- sha is a full 40-char commit that is an ancestor of HEAD (reachable once merged)
- the plugin dir is unchanged between the pinned sha and HEAD (pin isn't stale)
- name, version, requires_hermes and capabilities match the manifest
  (description may differ: the catalog adds a risk disclosure)
"""

from __future__ import annotations

import re
import subprocess
import sys

import yaml

entry = yaml.safe_load(open("plugin-catalog-entry.yaml"))
manifest = yaml.safe_load(open(f"{entry['subdir']}/plugin.yaml"))
errors = []


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


sha = str(entry.get("sha", ""))
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    errors.append(f"sha {sha!r} is not a full 40-char commit")
elif git("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
    errors.append(f"sha {sha} is not an ancestor of HEAD")
elif git("diff", "--quiet", sha, "HEAD", "--", entry["subdir"]).returncode != 0:
    errors.append(f"{entry['subdir']}/ changed after pinned sha {sha}; re-pin and bump version")

for key in ("name", "version", "requires_hermes"):
    if str(entry.get(key)) != str(manifest.get(key)):
        errors.append(f"{key}: entry {entry.get(key)!r} != plugin.yaml {manifest.get(key)!r}")

if entry.get("capabilities") != manifest.get("capabilities"):
    errors.append("capabilities differ between entry and plugin.yaml")

for e in errors:
    print(f"::error file=plugin-catalog-entry.yaml::{e}")
print("entry OK" if not errors else f"{len(errors)} problem(s)")
sys.exit(1 if errors else 0)
