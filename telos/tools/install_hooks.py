#!/usr/bin/env python3
"""Install git hooks from .githooks/ to .git/hooks/."""
import shutil, os, stat
hooks_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.githooks')
git_hooks = os.path.join(os.path.dirname(hooks_dir), '.git', 'hooks')
for f in os.listdir(hooks_dir):
    src = os.path.join(hooks_dir, f)
    dst = os.path.join(git_hooks, f)
    shutil.copy2(src, dst)
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installed: {dst}")
