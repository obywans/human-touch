"""Shared helpers for HumanTouch's update check/apply scripts.

Stdlib only, no third-party dependencies, so it works wherever python3 works.
Every function here is designed to fail safely: a network or parsing error
raises a plain Exception with a short, human-readable message, and the
callers (check_update.py / apply_update.py) are the ones that decide what
"fail safely" means for their situation. Nothing here ever touches the
network implicitly at import time, and nothing here executes any downloaded
content as code — only JSON is parsed and, in apply_update.py, a release
tarball's files are extracted and copied, never executed.
"""
from __future__ import annotations

import json
import os
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

OWNER = "obywans"
REPO = "human-touch"
API_LATEST_RELEASE = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"
OFFICIAL_REMOTE_RE = re.compile(
    rf"^(https://|git@)github\.com[:/]{OWNER}/{REPO}(\.git)?/?$", re.IGNORECASE
)
DEFAULT_TIMEOUT = 4  # seconds; never let a hung network call block /human
DEFAULT_THROTTLE_SECONDS = 3600  # check GitHub at most once per hour

# The source page this project's patterns were informed by. This is a
# notice-only check: it reports that the page changed, it never reads the
# page's content or changes SKILL.md on its own. A human reviews the change
# and decides what, if anything, to incorporate -- the same way every other
# change to SKILL.md has been made in this project.
WIKI_PAGE_TITLE = "Wikipedia:Signs of AI writing"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"


def url_host(url: str) -> str:
    """Real host of a URL ('' when there is none). Parsed, not split on '/', so
    'https://evil.example#.github.com/x' and 'https://api.github.com@evil.example/x'
    are read as evil.example."""
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_in(url: str, *domains: str) -> bool:
    """True when url's host is one of domains or a subdomain of one."""
    host = url_host(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def skill_dir_from_script(script_path: str) -> str:
    """scripts/check_update.py -> the skill directory (its parent's parent)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(script_path)))


def read_installed_version(skill_dir: str) -> str | None:
    path = os.path.join(skill_dir, "VERSION")
    try:
        with open(path, "r", encoding="utf-8") as f:
            v = f.read().strip()
        return v or None
    except OSError:
        return None


def parse_version(tag: str) -> tuple[int, ...]:
    """'v1.2.0' or '1.2.0' -> (1, 2, 0). Unparseable parts become 0."""
    tag = tag.strip()
    if tag.lower().startswith("v"):
        tag = tag[1:]
    parts = []
    for p in tag.split("."):
        m = re.match(r"\d+", p)
        parts.append(int(m.group()) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(latest_tag: str, installed_version: str) -> bool:
    return parse_version(latest_tag) > parse_version(installed_version)


def fetch_latest_release(
    timeout: float = DEFAULT_TIMEOUT, opener=urllib.request.urlopen
) -> dict:
    """Hits the fixed, hardcoded official API URL. Raises on any problem
    (network error, non-200, malformed JSON, missing "tag_name") — callers
    decide what to do; this function never swallows an error silently."""
    req = urllib.request.Request(
        API_LATEST_RELEASE,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "human-touch-update-check"},
    )
    with opener(req, timeout=timeout) as resp:
        # Guard against a redirect landing somewhere other than GitHub's own
        # infrastructure before we trust the body as "the official release".
        final_url = resp.geturl() or ""
        if "://" in final_url and not host_in(final_url, "github.com"):
            raise ValueError(f"unexpected redirect host: {url_host(final_url)!r}")
        raw = resp.read(1_000_000)  # cap: refuse to buffer an unbounded response
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"release response is a {type(data).__name__}, not a JSON object")
    tag = data.get("tag_name")
    if not tag or not isinstance(tag, str):
        raise ValueError("release response has no usable tag_name")
    return {
        "tag": tag,
        "name": data.get("name") or tag,
        "html_url": data.get("html_url") or f"https://github.com/{OWNER}/{REPO}/releases/tag/{tag}",
        "tarball_url": data.get("tarball_url"),
    }


def describe_fetch_error(exc: Exception) -> str:
    """Turns an exception from fetch_latest_release (or a download in
    apply_update.py) into a short, specific category instead of a generic
    "could not reach GitHub" for every failure. DNS, TLS, an HTTP error
    status, a timeout, and GitHub responding with something unusable are
    genuinely different situations and deserve different wording."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"GitHub returned HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return "DNS lookup failed"
        if isinstance(reason, ssl.SSLError):
            return f"TLS error ({reason})"
        if isinstance(reason, socket.timeout):
            return "connection timed out"
        return f"network error ({reason})"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timed out"
    if isinstance(exc, json.JSONDecodeError):
        return "GitHub responded, but not with valid JSON"
    if isinstance(exc, ValueError):
        return f"GitHub responded, but the release data was unusable: {exc}"
    return f"unexpected error: {exc}"


def fetch_wikipedia_revision(
    timeout: float = DEFAULT_TIMEOUT, opener=urllib.request.urlopen
) -> dict:
    """Returns {"revid": int, "timestamp": str} for the current revision of
    WIKI_PAGE_TITLE. Raises on any problem, same contract as
    fetch_latest_release -- callers decide what "fail safely" means."""
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "titles": WIKI_PAGE_TITLE,
            "rvprop": "ids|timestamp",
            "format": "json",
        }
    )
    req = urllib.request.Request(
        f"{WIKI_API_URL}?{params}",
        headers={"User-Agent": "human-touch-update-check"},
    )
    with opener(req, timeout=timeout) as resp:
        final_url = resp.geturl() or ""
        if "://" in final_url and not host_in(final_url, "wikipedia.org"):
            raise ValueError(f"unexpected redirect host: {url_host(final_url)!r}")
        raw = resp.read(1_000_000)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"Wikipedia response is a {type(data).__name__}, not a JSON object")
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise ValueError("Wikipedia response has no page data")
    page = next(iter(pages.values()))
    revisions = page.get("revisions") or []
    if not revisions or "revid" not in revisions[0]:
        raise ValueError("Wikipedia response has no usable revision")
    return {"revid": revisions[0]["revid"], "timestamp": revisions[0].get("timestamp")}


def cache_dir() -> str:
    base = os.environ.get("HUMAN_TOUCH_CACHE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "human-touch"
    )
    return base


def state_path() -> str:
    return os.path.join(cache_dir(), "update-state.json")


def load_state() -> dict:
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def save_state(state: dict) -> None:
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        tmp = state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, state_path())
    except OSError:
        pass  # caching is an optimization, never a requirement


def should_check(
    state: dict, throttle_seconds: int = DEFAULT_THROTTLE_SECONDS, key: str = "last_checked_epoch"
) -> bool:
    """Same cache/throttle mechanism for any timed check this state dict
    tracks -- the GitHub release check uses the default key, the Wikipedia
    notice check below uses its own key, so one check running doesn't reset
    the other's clock."""
    last = state.get(key)
    if not isinstance(last, (int, float)):
        return True
    return (time.time() - last) >= throttle_seconds


def git_remote_is_official(repo_dir: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False
    return bool(OFFICIAL_REMOTE_RE.match(out))


def git_working_tree_clean(repo_dir: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir, "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False
    return out.strip() == ""


PLUGIN_UPDATE_NOTICE = (
    "This copy is a plugin install of an old version. Plugin updates do not reach version 3.x. "
    "Run the two commands of the README section 'Move from the plugin route'."
)


def skill_dir_writable(skill_dir: str) -> bool:
    """True when the skill folder and its VERSION file can be written.
    A package install (claude.ai zip, Desktop extension) usually cannot."""
    try:
        return os.access(skill_dir, os.W_OK) and os.access(os.path.join(skill_dir, "VERSION"), os.W_OK)
    except OSError:
        return False


def is_plugin_cache(skill_dir: str) -> bool:
    """True when skill_dir lives in Claude Code's plugin cache
    (~/.claude/plugins/cache/... or .../plugins/marketplaces/...). Claude Code owns those files and replaces the
    whole version directory on `plugin update`; writing into it from here would
    fight the plugin manager, so a plugin install is never self-updated by this
    code. The skill tells the user to move to the skill folder instead."""
    parts = os.path.realpath(skill_dir).replace("\\", "/").lower().split("/")
    return any(a == "plugins" and b in ("cache", "marketplaces") for a, b in zip(parts, parts[1:]))


def detect_install_mode(skill_dir: str) -> str:
    """'plugin' | 'git-official' | 'git-other' | 'copy'. Walks up from skill_dir
    to find a .git directory the way `git -C skill_dir rev-parse` would."""
    if is_plugin_cache(skill_dir):
        return "plugin"
    try:
        is_repo = subprocess.run(
            ["git", "-C", skill_dir, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() == "true"
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        is_repo = False
    if not is_repo:
        return "copy"
    try:
        top = subprocess.run(
            ["git", "-C", skill_dir, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return "copy"
    return "git-official" if git_remote_is_official(top) else "git-other"
