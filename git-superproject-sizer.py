#!/usr/bin/env python3

import argparse
import json
import csv
import subprocess
import sys
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from multiprocessing import cpu_count

PROJECT_ROOT = Path(__file__).parent


def sanitize_url(url: str) -> str:
    """Convert a git URL to a valid directory name."""
    # Remove protocol and trailing .git
    url = re.sub(r'^https?://|^git@|\.git$', '', url)
    # Replace invalid characters with underscores
    url = re.sub(r'[^a-zA-Z0-9-]', '_', url)
    return url


def get_cache_dir() -> Path:
    """Get the cache directory path."""
    cache_dir = Path.home() / '.cache' / 'git-superproject-sizer'
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def get_submodule_config() -> Dict[str, Dict[str, str]]:
    config_result = subprocess.run(
        ["git", "config", "--file", ".gitmodules", "-l"],
        capture_output=True,
        text=True,
        check=True,
    )
    submodules = {}
    for config_line in config_result.stdout.splitlines():
        if not config_line.startswith("submodule."):
            continue
        key, value = config_line.split("=", 1)
        if not key.endswith("path"):
            continue
        submodule_name = key[len("submodule."):-len(".path")]
        submodules[submodule_name] = {"path": value}

    config_result = subprocess.run(
        ["git", "config", "-l"],
        capture_output=True,
        text=True,
        check=True,
    )

    for config_line in config_result.stdout.splitlines():
        if not config_line.startswith("submodule."):
            continue
        key, value = config_line.split("=", 1)
        if not key.endswith("url"):
            continue
        submodule_name = key[len("submodule."):-len(".url")]
        submodules[submodule_name]["url"] = value
        
    return {submodules[submodule_name]["path"]: submodules[submodule_name]["url"] for submodule_name in submodules}


def get_submodule_info(skip_paths: Set[str]) -> List[Tuple[str, str, str]]:
    """Get all submodule information (path, url, commit) excluding skipped ones."""
    try:
        result = subprocess.run(
            ["git", "submodule", "status", "--recursive"],
            capture_output=True,
            text=True,
            check=True,
        )

        path_path_mapping = get_submodule_config()

        submodules = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: <commit> <path> (<branch>)
            parts = line.split()
            if len(parts) < 2:
                continue
            commit = parts[0].lstrip("-+")
            submodule_path = parts[1]
            if submodule_path in skip_paths:
                continue

            if submodule_path not in path_path_mapping:
                print(f"Warning: Submodule {submodule_path} not found in .gitmodules", file=sys.stderr)
                continue
            
            submodules.append((submodule_path, path_path_mapping[submodule_path], commit))
        
        return submodules
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to get submodule info: {e}", file=sys.stderr)
        sys.exit(1)


def get_repo_size(url: str, commit: str) -> Optional[int]:
    """Get the size of a repository using git-worktree-sizer.py with a bare repository."""
    cache_dir = get_cache_dir()
    repo_dir = cache_dir / sanitize_url(url)
    
    try:
        # Create or update the bare clone
        if not repo_dir.exists():
            subprocess.run(
                ["git", "init", "--bare", str(repo_dir)],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "add", "origin", url],
                capture_output=True,
                check=True,
            )
        print(f"\rFetching {url}...", end="", file=sys.stderr)
        # Update the existing clone
        subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "--filter=blob:none", "origin", commit],
            capture_output=True,
            check=True,
        )
        
        # Get the size using git-worktree-sizer.py
        result = subprocess.run(
            [PROJECT_ROOT / "git-worktree-sizer.py"), commit],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to get size for {url}@{commit}: {e.stderr}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Compute the total size of all submodules in a git superproject using bare clones"
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--skip",
        action="append",
        help="Skip specific submodule paths (can be specified multiple times)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache directory before running",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=cpu_count(),
        help="Maximum number of worker threads (default: number of CPU cores)",
    )

    args = parser.parse_args()
    skip_paths = set(args.skip or [])

    if args.clear_cache:
        cache_dir = get_cache_dir()
        if cache_dir.exists():
            for item in cache_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

    # Initialize submodules
    try:
        subprocess.run(
            ["git", "submodule", "init"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error initializing submodules: {e.stderr}", file=sys.stderr)
        sys.exit(1)

    submodule_info = get_submodule_info(skip_paths)
    results: Dict[str, Optional[int]] = {}

    # Process submodules in parallel
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_path = {
            executor.submit(get_repo_size, url, commit): path
            for path, url, commit in submodule_info
        }
        
        for future in future_to_path:
            path = future_to_path[future]
            try:
                size = future.result()
                results[path] = size
            except Exception as e:
                print(f"Error processing {path}: {e}", file=sys.stderr)
                results[path] = None

    # Output results
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:  # CSV
        writer = csv.writer(sys.stdout)
        writer.writerow(["path", "size"])
        for path, size in results.items():
            writer.writerow([path, size if size is not None else ""])


if __name__ == "__main__":
    main() 