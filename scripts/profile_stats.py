"""Generate aggregate profile cards using only Python's standard library and GitHub."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUMMARY_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  viewer { login }
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
    }
  }
}
"""

REPOSITORIES_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        isFork
        stargazerCount
        languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
          pageInfo { hasNextPage }
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

START = "<!-- profile-stats:start -->"
END = "<!-- profile-stats:end -->"


def graphql(token, query, variables):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "freeloadsk-profile-stats",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except HTTPError as error:
        # Never print a response body: it might contain private repository details.
        raise RuntimeError(f"GitHub API returned HTTP {error.code}; check token access and limits.") from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError("GitHub API request failed; existing cards were preserved.") from None
    if payload.get("errors") or not payload.get("data"):
        raise RuntimeError("GitHub GraphQL query failed; check token permissions and SSO authorization.")
    return payload["data"]


def collect(login, token, now=None, request=graphql):
    now = now or datetime.now(timezone.utc)
    data = request(token, SUMMARY_QUERY, {
        "login": login,
        "from": (now - timedelta(days=365)).isoformat(),
        "to": now.isoformat(),
    })
    if data["viewer"]["login"].casefold() != login.casefold():
        raise RuntimeError("The token must belong to the profile owner.")
    user = data.get("user")
    if not user:
        raise RuntimeError("GitHub profile was not found.")
    activity = user["contributionsCollection"]
    stats = {
        "Stars earned": 0,
        "Commits (365 days)": activity["totalCommitContributions"],
        "Pull requests (365 days)": activity["totalPullRequestContributions"],
        "Issues (365 days)": activity["totalIssueContributions"],
        "Reviews (365 days)": activity["totalPullRequestReviewContributions"],
    }
    sizes, colors = Counter(), {}
    cursor, seen = None, set()
    while True:
        data = request(token, REPOSITORIES_QUERY, {"login": login, "cursor": cursor})
        repositories = data["user"]["repositories"]
        for repo in repositories["nodes"]:
            # Forks do not represent the profile owner's original code.
            if repo["isFork"]:
                continue
            stats["Stars earned"] += repo["stargazerCount"]
            languages = repo["languages"]
            if languages["pageInfo"]["hasNextPage"]:
                raise RuntimeError("A repository has over 100 languages; refusing to publish incomplete totals.")
            for edge in languages["edges"]:
                name = edge["node"]["name"]
                sizes[name] += edge["size"]
                colors[name] = edge["node"]["color"]
        page = repositories["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
        if not cursor or cursor in seen:
            raise RuntimeError("GitHub returned an invalid pagination cursor.")
        seen.add(cursor)
    return stats, sizes, colors


def card(title, subtitle, body, height=300):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="{height}" viewBox="0 0 480 {height}" role="img" aria-labelledby="title subtitle">
  <title id="title">{escape(title)}</title>
  <desc id="subtitle">{escape(subtitle)}</desc>
  <style>
    :root {{ color-scheme: light dark; --bg:#ffffff; --line:#d0d7de; --text:#1f2328; --muted:#59636e; --accent:#0969da; --track:#eaeef2; }}
    @media (prefers-color-scheme:dark) {{ :root {{ --bg:#0d1117; --line:#30363d; --text:#e6edf3; --muted:#9198a1; --accent:#58a6ff; --track:#21262d; }} }}
    text {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-size:13px; fill:var(--text); }}
    .title {{ font-size:19px; font-weight:650; fill:var(--accent); }}
    .muted {{ fill:var(--muted); font-size:11px; }}
    .value {{ font-weight:650; font-variant-numeric:tabular-nums; }}
  </style>
  <rect x="0.5" y="0.5" width="479" height="{height - 1}" rx="12" fill="var(--bg)" stroke="var(--line)"/>
  <text x="24" y="37" class="title">{escape(title)}</text>
  <text x="24" y="60" class="muted">{escape(subtitle)}</text>
  {body}
</svg>
'''


def stats_card(login, stats):
    body = []
    for index, (label, value) in enumerate(stats.items()):
        y = 96 + index * 31
        body.append(f'<text x="24" y="{y}">{escape(label)}</text>')
        body.append(f'<text x="456" y="{y}" text-anchor="end" class="value">{value:,}</text>')
    return card(f"{login}'s GitHub Stats", "Public + accessible private activity", "\n  ".join(body))


def languages_card(sizes, colors):
    total = sum(sizes.values())
    body = []
    if not total:
        body.append('<text x="24" y="112">No language data available.</text>')
    else:
        # Percentages use all language bytes, including languages outside the top six.
        for index, (name, size) in enumerate(sizes.most_common(6)):
            y = 90 + index * 32
            share = size / total
            color = colors.get(name) or "#6e7781"
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                color = "#6e7781"
            body.append(f'<text x="24" y="{y}">{escape(name)}</text>')
            body.append(f'<text x="456" y="{y}" text-anchor="end" class="value">{share:.1%}</text>')
            body.append(f'<rect x="24" y="{y + 8}" width="432" height="5" rx="2.5" fill="var(--track)"/>')
            body.append(f'<rect x="24" y="{y + 8}" width="{432 * share:.2f}" height="5" rx="2.5" fill="{color}"/>')
    return card("Most Used Languages", "Original owned repositories · public + accessible private", "\n  ".join(body))


def publish(root, login, stats, sizes, colors):
    readme = root / "README.md"
    # Keep the file's original line endings and preserve all content outside our markers.
    text = readme.read_bytes().decode("utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise RuntimeError("README must contain exactly one profile-stats marker pair.")
    start = text.index(START) + len(START)
    end = text.index(END)
    if end < start:
        raise RuntimeError("README profile-stats markers are out of order.")
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline + newline.join([
        "[![GitHub Stats](./profile/stats.svg)](./docs/profile-stats.md)",
        "[![Top Languages](./profile/top-langs.svg)](./docs/profile-stats.md)",
    ]) + newline
    # Fetching, pagination and rendering must all succeed before any files are written.
    outputs = {"stats.svg": stats_card(login, stats), "top-langs.svg": languages_card(sizes, colors)}
    output = root / "profile"
    output.mkdir(exist_ok=True)
    for filename, svg in outputs.items():
        (output / filename).write_text(svg, encoding="utf-8", newline="\n")
    readme.write_bytes((text[:start] + block + text[end:]).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    token = os.environ.get("PROFILE_STATS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Add the PROFILE_STATS_TOKEN repository secret, then run this workflow again.")
    stats, sizes, colors = collect(args.username, token)
    publish(args.root, args.username, stats, sizes, colors)
    print("Updated aggregate SVG cards and README. No repository details were saved.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
        # Do not dump objects, request headers, or API payloads into public workflow logs.
        message = str(error) if isinstance(error, RuntimeError) else "Generation failed; existing published cards were preserved."
        print(message, file=sys.stderr)
        sys.exit(1)
