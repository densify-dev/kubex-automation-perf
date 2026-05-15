#!/usr/bin/env python3
"""Helm post-renderer that removes the Kubex self-pause annotation."""

from __future__ import annotations

import sys

import yaml


PAUSE_ANNOTATION = "rightsizing.kubex.ai/pause-until"


def strip_pause(doc: dict) -> None:
    template = doc.get("spec", {}).get("template", {})
    metadata = template.get("metadata", {})
    annotations = metadata.get("annotations")
    if isinstance(annotations, dict) and PAUSE_ANNOTATION in annotations:
        del annotations[PAUSE_ANNOTATION]


def main() -> int:
    docs = list(yaml.safe_load_all(sys.stdin))
    for doc in docs:
        if isinstance(doc, dict):
            strip_pause(doc)
    yaml.safe_dump_all(docs, sys.stdout, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
