#!/usr/bin/env python3
"""Citation pages for one person, from a Google Scholar profile and OpenAlex.

    python3 code/citestory.py update profiles/<name>     fetch a new snapshot, then build the site
    python3 code/citestory.py build  profiles/<name>     rebuild the site from the last snapshot
    python3 code/citestory.py update profiles/<name> --restart   discard an unfinished refresh and start again

A profile folder holds profile.json (who), data/ (snapshots, written by update) and site/ (the pages, written by
build). See README.md for the profile.json fields.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import build_citation_geo
import fetch_citation_geo

KNOWN = {"name", "scholar_url", "scholar_html", "aliases", "home", "openalex_author_ids", "deploy_to"}


def load_profile(folder):
    path = folder / "profile.json"
    if not path.is_file():
        raise SystemExit(f"{path} not found. Create it with at least {{\"scholar_url\": \"https://scholar.google.com/citations?user=…\"}}.")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}")
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must hold a JSON object, such as {{\"scholar_url\": \"…\"}}.")
    unknown = set(config) - KNOWN
    if unknown:
        raise SystemExit(f"Unknown profile.json field(s): {', '.join(sorted(unknown))}. Known: {', '.join(sorted(KNOWN))}.")
    for key in ("name", "scholar_url", "scholar_html", "home", "deploy_to"):
        if config.get(key) is not None and not isinstance(config[key], str):
            raise SystemExit(f"\"{key}\" in {path} must be a string.")
    for key in ("scholar_html", "deploy_to"):
        if config.get(key):
            config[key] = str((folder / Path(config[key]).expanduser()).resolve())
    if not isinstance(config.get("aliases", []), list) or not isinstance(config.get("openalex_author_ids", []), list):
        raise SystemExit("\"aliases\" and \"openalex_author_ids\" must be lists.")
    return config


def deploy(site, target):
    """Copy the built pages and data files into the website folder (e.g. <al-folio>/assets/citation-geography)."""
    target.mkdir(parents=True, exist_ok=True)
    names = build_citation_geo.PAGES + build_citation_geo.DATA_FILES
    for name in names:
        shutil.copy2(site / name, target / name)
    print(f"Copied {len(names)} files to {target}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["update", "build"])
    parser.add_argument("profile", type=Path, help="profile folder, e.g. profiles/feisun")
    parser.add_argument("--restart", action="store_true", help="discard an unfinished refresh (update)")
    parser.add_argument("--max-requests", type=int, default=fetch_citation_geo.REQUEST_BUDGET,
                        help="OpenAlex requests allowed this run; an interrupted refresh resumes next run")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):    # names in any script print even to a non-UTF-8 console or log
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    folder = args.profile.resolve()
    config = load_profile(folder)
    data, site = folder / "data", folder / "site"
    data.mkdir(parents=True, exist_ok=True)
    fresh = True
    if args.action == "update":
        fresh = fetch_citation_geo.refresh(config, data, restart=args.restart, max_requests=args.max_requests)
        if not fresh:
            if not (data / "manifest.json").exists():
                return 1
            print("Building from the previous snapshot.", flush=True)
    build_citation_geo.build(data, site)
    print(f"Site: {site}", flush=True)
    if config.get("deploy_to"):
        deploy(site, Path(config["deploy_to"]))
    return 0 if fresh else 2


if __name__ == "__main__":
    sys.exit(main())
