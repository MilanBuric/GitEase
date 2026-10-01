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

build_authed_url() always strips any credentials already embedded in
the URL before adding new ones. This matters for a real failure mode:
a repo cloned by a pre-credential-safety build of GitEase can have a
token permanently baked into its stored origin URL. Without stripping
first, applying a new token on top produces a doubly-credentialed URL
like https://newtoken@oldtoken@host/... -- which git/curl reject
outright with "URL rejected: Bad hostname", and which also means the
OLD token gets logged in full the next time that URL is read, even
though GitEase's own logging code only ever intended to log a clean
URL. Stripping first makes every call here idempotent and self-healing,
regardless of a repo's history.
"""

from contextlib import contextmanager
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


def strip_existing_credentials(url):
    """Removes any username/token already embedded in an https:// URL's
    authority section, returning a clean URL. SSH URLs (ssh:// or the
    scp-like git@host: syntax) are returned unchanged -- their "user@host"
    is legitimate git protocol syntax, not a credential to strip."""
    if not url.startswith("https://"):
        return url
    parsed = urlparse(url)
    netloc = parsed.netloc
    if "@" in netloc:
        # Split on the LAST '@' -- if an old token somehow itself
        # contained '@', this still finds the real host correctly.
        netloc = netloc.rsplit("@", 1)[1]
    return parsed._replace(netloc=netloc).geturl()


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
    host expects, after first stripping any credential already present
    in the URL (see module docstring for why that matters). SSH URLs
    and untokened URLs are returned unchanged."""
    if not token or not url.startswith("https://"):
        return url

    clean_url = strip_existing_credentials(url)
    host = _host_of(clean_url)
    username = ""
    for domain, user in PROVIDER_USERNAMES.items():
        if domain in host:
            username = user
            break

    if username:
        return clean_url.replace("https://", f"https://{username}:{token}@", 1)
    return clean_url.replace("https://", f"https://{token}@", 1)


@contextmanager
def temporarily_authed_remote(repo, token, remote_name="origin"):
    """Temporarily rewrites a remote's URL to embed a token for the
    duration of exactly one git network operation (pull/push/fetch),
    then always restores a clean, token-free URL afterward -- even if
    the operation raises. This is what keeps a token from ending up
    sitting in plaintext in .git/config permanently: it's only ever
    there for the few seconds a real network call is in flight, never
    at rest.

    Self-healing: if the remote's stored URL already has a stale
    credential baked in (e.g. from a repo cloned by an older build of
    GitEase, before this protection existed), that's cleaned up here
    too -- regardless of whether a new token is being applied -- so a
    repo's stored URL converges to clean the next time it's touched,
    rather than staying permanently dirty.

    If there's no token, or the remote is SSH-based, the embed/restore
    cycle is skipped, but a dirty stored URL is still healed if found.
    """
    remote = repo.remotes[remote_name]
    original_url = remote.url
    clean_url = strip_existing_credentials(original_url)

    if not token:
        if clean_url != original_url:
            remote.set_url(clean_url)
        yield remote
        return

    authed_url = build_authed_url(clean_url, token)
    if authed_url == clean_url:
        # SSH, or otherwise nothing to embed -- still heal a dirty URL if found.
        if clean_url != original_url:
            remote.set_url(clean_url)
        yield remote
        return

    remote.set_url(authed_url)
    try:
        yield remote
    finally:
        remote.set_url(clean_url)