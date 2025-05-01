# Git Worktree Sizer

A simple script that computes size of a worktree - a git checkout size without .git entry. All you need to do is specify <committish>.

Note: If you need a quick and dirty estimate, you can just use:

```
    git ls-tree -l -r <committish> | less | awk '{sum += $4} END {print sum}' 
```

## Overview

This script helps you manage your Git worktrees by:
- Showing the size of each worktree (e.g. HEAD, )
- Identifying potential cleanup candidates
- Providing a summary of worktree usage

## Requirements

- Python 3.x
- Git

## Usage

```bash
python git_worktree_sizer.py <committish>
```

## Development

This project was primarily developed with the assistance of LLMs.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 