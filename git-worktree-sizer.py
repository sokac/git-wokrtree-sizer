#!/usr/bin/env python3

import argparse
import subprocess
import sys
from enum import Enum
from typing import Optional


class Unit(Enum):
    BYTES = "bytes"
    KIB = "KiB"
    MIB = "MiB"
    GIB = "GiB"

    def convert(self, size_in_bytes: int) -> float:
        match self:
            case Unit.BYTES:
                return size_in_bytes
            case Unit.KIB:
                return size_in_bytes / 1024
            case Unit.MIB:
                return size_in_bytes / (1024 * 1024)
            case Unit.GIB:
                return size_in_bytes / (1024 * 1024 * 1024)


def get_block_size() -> int:
    """Get filesystem block size."""
    try:
        # Try to get the block size from the git directory
        result = subprocess.run(
            ["stat", "-f", "-c", "%S", ".git"],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        # Fallback to default 4096 if we can't determine it
        return 4096


def round_to_block_size(size: int, block_size: int) -> int:
    """Round up size to the nearest block boundary."""
    return ((size + block_size - 1) // block_size) * block_size


def get_tree_hash(ref: str) -> str:
    """Get the tree hash for a given git reference."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{ref}^{{tree}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: Invalid git reference '{ref}'", file=sys.stderr)
        sys.exit(1)


def get_total_size(tree_hash: str, block_size: int) -> int:
    """Get total size of all blobs in the tree."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-l", "-r", tree_hash],
            capture_output=True,
            text=True,
            check=True,
        )
        
        total_size = 0
        for line in result.stdout.splitlines():
            # Format: <mode> <type> <object> <size> <path>
            parts = line.split()
            if len(parts) >= 4 and parts[1] == "blob":
                # Round up each file's size to block boundary
                file_size = int(parts[3])
                block_aligned_size = round_to_block_size(file_size, block_size)
                total_size += block_aligned_size
        
        return total_size
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to get tree contents: {e.stderr}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Compute the total size of files in a git commit, accounting for filesystem block size"
    )
    parser.add_argument(
        "reference",
        help="Git reference (commit-ish) to analyze",
    )
    parser.add_argument(
        "--unit",
        type=Unit,
        choices=list(Unit),
        default=Unit.BYTES,
        help="Output unit (default: bytes)",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        help="Override filesystem block size (default: auto-detect)",
    )

    args = parser.parse_args()

    # Get or use provided block size
    block_size = args.block_size if args.block_size else get_block_size()

    # Get the tree hash for the reference
    tree_hash = get_tree_hash(args.reference)
    
    # Calculate total size
    total_size = get_total_size(tree_hash, block_size)
    
    # Convert to requested unit
    converted_size = args.unit.convert(total_size)
    
    # Print just the number
    print(int(converted_size) if args.unit == Unit.BYTES else converted_size)


if __name__ == "__main__":
    main() 