"""
Unit tests for git_providers.build_authed_url / detect_provider --
confirms each host gets the auth format it actually expects.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from git_providers import build_authed_url, detect_provider


def test_github_uses_token_only():
    url = build_authed_url("https://github.com/user/repo.git", "abc123")
    assert url == "https://abc123@github.com/user/repo.git"


def test_gitlab_uses_oauth2_username():
    url = build_authed_url("https://gitlab.com/user/repo.git", "abc123")
    assert url == "https://oauth2:abc123@gitlab.com/user/repo.git"


def test_bitbucket_uses_x_token_auth_username():
    url = build_authed_url("https://bitbucket.org/user/repo.git", "abc123")
    assert url == "https://x-token-auth:abc123@bitbucket.org/user/repo.git"


def test_unknown_host_falls_back_to_token_only():
    url = build_authed_url("https://git.example.com/user/repo.git", "abc123")
    assert url == "https://abc123@git.example.com/user/repo.git"


def test_ssh_url_untouched_regardless_of_host():
    url = build_authed_url("git@gitlab.com:user/repo.git", "abc123")
    assert url == "git@gitlab.com:user/repo.git"


def test_no_token_returns_url_unchanged():
    url = build_authed_url("https://gitlab.com/user/repo.git", None)
    assert url == "https://gitlab.com/user/repo.git"


def test_detect_provider_labels():
    assert detect_provider("https://github.com/user/repo.git") == "GitHub"
    assert detect_provider("https://gitlab.com/user/repo.git") == "GitLab"
    assert detect_provider("https://bitbucket.org/user/repo.git") == "Bitbucket"
    assert detect_provider("https://git.example.com/user/repo.git") == "Other"
    assert detect_provider("git@gitlab.com:user/repo.git") == "GitLab"