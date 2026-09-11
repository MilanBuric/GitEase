"""
Provider-aware credential embedding for git URLs.

GitHub, GitLab, and Bitbucket each expect a slightly different
username alongside a token when authenticating over HTTPS:

  - GitHub:    https://<token>@host/...
  - GitLab:    https://oauth2:<token>@host/...
  - Bitbucket: https://x-token-auth:<token>@host/...   (App Password)

detect_provider() is for display only. build_authed_url() is what
CloneWorker and BranchListWorker actually use -- it inspects the
URL's host and injects the token in the format that host expects,
falling back to the generic "token as username" format (which also
works for most self-hosted git servers) for anything unrecognized.
SSH URLs and URLs with no token are returned unchanged.
"""

from urllib.parse import urlparse

# domain substring -> username to pair with the token
PROVIDER_USERNAMES = {
    "github.com": "",                  # GitHub: no fixed username, token alone
    "gitlab.com": "oauth2",
    "bitbucket.org": "x-token-auth",
}

PROVIDER_LABELS = {
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "bitbucket.org": "Bitbucket",
}


def _host_of(url):
    if "://" in url:
        return urlparse(url).netloc.lower()
    if "@" in url and ":" in url:
        # scp-like SSH syntax, e.g. git@github.com:user/repo.git
        return url.split("@", 1)[1].split(":", 1)[0].lower()
    return ""


def detect_provider(url):
    """Returns a short provider label for display purposes."""
    host = _host_of(url)
    if not host:
        return "Unknown"
    for domain, label in PROVIDER_LABELS.items():
        if domain in host:
            return label
    return "Other"


def build_authed_url(url, token):
    """Injects a token into an https:// URL using the auth format the
    host expects. SSH URLs and untokened URLs are returned unchanged."""
    if not token or not url.startswith("https://"):
        return url

    host = _host_of(url)
    username = ""
    for domain, user in PROVIDER_USERNAMES.items():
        if domain in host:
            username = user
            break

    if username:
        return url.replace("https://", f"https://{username}:{token}@", 1)
    return url.replace("https://", f"https://{token}@", 1)