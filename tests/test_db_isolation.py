"""Guards that the test DB path is per-worktree, not a shared fixed file.

A fixed /tmp/gitd_pytest.db is shared by every checkout, so pytest running
concurrently in two per-agent worktrees races on the same file (one session's
clean-slate unlink+create clobbers the other → intermittent "no such table" /
locked failures). conftest keys the path to the worktree root instead.
"""

import hashlib
import os
from pathlib import Path


def _worktree_key():
    # Must match the derivation in tests/conftest.py.
    root = Path(__file__).resolve().parent.parent
    return hashlib.md5(str(root).encode()).hexdigest()[:8]


def test_db_path_is_worktree_keyed():
    db = os.environ.get("DB_PATH", "")
    # Not the old shared fixed name (that was the collision source).
    assert not db.endswith("gitd_pytest.db"), "test DB uses the old shared fixed path"
    # Keyed to THIS worktree so concurrent runs in other worktrees don't collide.
    assert f"gitd_pytest_{_worktree_key()}.db" in db


def test_different_worktrees_get_different_paths():
    """The keying must actually separate distinct checkouts."""
    k1 = hashlib.md5(b"/home/agent/worktrees/core-dev").hexdigest()[:8]
    k2 = hashlib.md5(b"/home/agent/worktrees/reviewer").hexdigest()[:8]
    assert k1 != k2
