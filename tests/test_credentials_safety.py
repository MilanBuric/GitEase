"""
Tests for the credential-safety behavior added to fix "token ends up
sitting in plaintext in .git/config": temporarily_authed_remote must
always restore the clean URL, even when the wrapped operation raises,
and CloneWorker must strip the token from the newly-cloned repo's
remote immediately after cloning.
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from git_providers import temporarily_authed_remote
from clone_worker import CloneWorker


class DummySignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args if len(args) > 1 else (args[0] if args else None))


def _make_mock_repo(url):
    repo = MagicMock()
    remote = MagicMock()
    remote.url = url

    def set_url(new_url):
        remote.url = new_url

    remote.set_url.side_effect = set_url
    repo.remotes.origin = remote
    repo.remotes.__getitem__.return_value = remote
    return repo, remote


def test_temp_auth_restores_clean_url_on_success():
    repo, remote = _make_mock_repo("https://github.com/user/repo.git")
    with temporarily_authed_remote(repo, "secret123") as r:
        assert r.url == "https://secret123@github.com/user/repo.git"
    assert remote.url == "https://github.com/user/repo.git"


def test_temp_auth_restores_clean_url_even_on_exception():
    repo, remote = _make_mock_repo("https://github.com/user/repo.git")
    try:
        with temporarily_authed_remote(repo, "secret123") as r:
            assert r.url == "https://secret123@github.com/user/repo.git"
            raise RuntimeError("simulated network failure mid-operation")
    except RuntimeError:
        pass
    # The whole point of this fix: even a mid-operation crash must not
    # leave the token sitting in the remote URL.
    assert remote.url == "https://github.com/user/repo.git"
    assert "secret123" not in remote.url


def test_temp_auth_is_noop_without_token():
    repo, remote = _make_mock_repo("https://github.com/user/repo.git")
    with temporarily_authed_remote(repo, None) as r:
        assert r.url == "https://github.com/user/repo.git"
    assert remote.set_url.call_count == 0


@patch("clone_worker.Repo.clone_from")
def test_clone_strips_token_from_stored_remote(mock_clone_from):
    mock_repo = MagicMock()
    mock_repo.remotes.origin.url = "https://SECRETTOKEN@github.com/user/repo.git"

    def set_url(new_url):
        mock_repo.remotes.origin.url = new_url

    mock_repo.remotes.origin.set_url.side_effect = set_url
    mock_clone_from.return_value = mock_repo

    dest = tempfile.mkdtemp()
    os.rmdir(dest)
    worker = CloneWorker("https://github.com/user/repo.git", dest, token="SECRETTOKEN")
    worker.log_message = DummySignal()
    worker.progress_percent = DummySignal()
    worker.finished_ok = DummySignal()
    worker.failed = DummySignal()

    worker.run()

    # The remote must have been rewritten back to the clean URL --
    # set_url should have been called with no token in it.
    mock_repo.remotes.origin.set_url.assert_called_once_with(
        "https://github.com/user/repo.git"
    )
    assert mock_repo.remotes.origin.url == "https://github.com/user/repo.git"
    # And nothing logged should contain the raw token either.
    assert not any("SECRETTOKEN" in str(entry) for entry in worker.log_message.emitted)


# ---------------- Progress bar monotonic guard ----------------

def test_progress_bar_never_regresses_even_for_unknown_stage():
    """Regression test: an earlier version of _STAGE_WEIGHTS didn't cover
    every op-code GitPython can report (WRITING and FINDING_SOURCES were
    missing), which could make the bar visibly jump backward mid-clone.
    The monotonic floor added to fix that must hold for ANY stage code,
    including ones this table has never seen."""
    from clone_worker import CloneProgress
    from git import RemoteProgress

    log_sig, pct_sig = DummySignal(), DummySignal()
    cp = CloneProgress(log_sig, pct_sig)

    sequence = [
        (RemoteProgress.COUNTING, 100, 100),
        (RemoteProgress.RECEIVING, 1000, 1000),
        (RemoteProgress.RESOLVING, 60, 60),
        (9999, 1, 100),  # a stage code the weight table has never heard of
        (RemoteProgress.CHECKING_OUT, 10, 10),
    ]
    for op, cur, mx in sequence:
        cp.update(op, cur, mx)

    values = pct_sig.emitted
    assert all(values[i] <= values[i + 1] for i in range(len(values) - 1)), (
        f"progress bar regressed: {values}"
    )


# ---------------- Double-credential / stale-token healing ----------------
# Regression coverage for a real bug: a repo cloned by an older,
# pre-credential-safety build of GitEase can have a token permanently
# baked into its stored origin URL. Applying a new token on top of that
# used to produce a doubly-credentialed URL (https://new@old@host/...),
# which git/curl reject outright, AND which leaked the old token into
# the log the next time that URL was read for display purposes.

def test_build_authed_url_strips_existing_token_before_adding_new_one():
    from git_providers import build_authed_url

    already_dirty_url = "https://gho_OLDTOKEN123@github.com/user/repo.git"
    result = build_authed_url(already_dirty_url, "gho_NEWTOKEN456")

    assert "OLDTOKEN123" not in result
    assert result.count("gho_NEWTOKEN456") == 1
    assert result.count("@") == 1
    assert result == "https://gho_NEWTOKEN456@github.com/user/repo.git"


def test_strip_existing_credentials_leaves_clean_url_unchanged():
    from git_providers import strip_existing_credentials

    clean = "https://github.com/user/repo.git"
    assert strip_existing_credentials(clean) == clean


def test_strip_existing_credentials_ignores_ssh_urls():
    from git_providers import strip_existing_credentials

    # git@host:path is legitimate SSH syntax, not a credential to strip
    ssh_url = "git@github.com:user/repo.git"
    assert strip_existing_credentials(ssh_url) == ssh_url


def test_temporarily_authed_remote_self_heals_a_dirty_stored_url():
    """The core fix: a repo whose remote already has a stale token baked
    in must end up with a fully clean URL in .git/config after any
    operation goes through temporarily_authed_remote -- not just during
    that one operation, but persisted afterward too."""
    from git_providers import temporarily_authed_remote

    repo, remote = _make_mock_repo(
        "https://gho_OLDTOKEN123@github.com/user/repo.git"
    )
    with temporarily_authed_remote(repo, "gho_NEWTOKEN456") as r:
        assert "OLDTOKEN123" not in r.url
        assert r.url == "https://gho_NEWTOKEN456@github.com/user/repo.git"

    assert remote.url == "https://github.com/user/repo.git"
    assert "OLDTOKEN123" not in remote.url
    assert "NEWTOKEN456" not in remote.url


def test_temporarily_authed_remote_heals_dirty_url_even_with_no_token():
    """A dirty stored URL should get cleaned up even on an operation that
    isn't applying any new token at all (e.g. a public repo pulled with
    no token configured, but which still has an old one baked in from
    before the fix existed)."""
    from git_providers import temporarily_authed_remote

    repo, remote = _make_mock_repo(
        "https://gho_OLDTOKEN123@github.com/user/repo.git"
    )
    with temporarily_authed_remote(repo, None) as r:
        assert r.url == "https://github.com/user/repo.git"

    assert remote.url == "https://github.com/user/repo.git"