from urllib.parse import urlparse, urlunparse

import requests

from config import load_config


BLOCKED_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "wikipedia.org",
    "crunchbase.com",
    "glassdoor.com",
    "indeed.com",
    "google.com",
    "maps.google.com",
    "bloomberg.com",
    "reuters.com",
    "forbes.com",
    "trade.gov",
    "fda.gov",
    "mfds.go.kr",
}

BLOCKED_DOMAIN_SUFFIXES = (".gov", ".go.kr", ".edu", ".ac.kr")
BLOCKED_FILE_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")


def get_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    parsed = parsed._replace(fragment="")
    return urlunparse(parsed)


def is_blocked_url(url: str) -> bool:
    normalized = normalize_url(url)
    if not normalized:
        return True

    parsed = urlparse(normalized)
    domain = get_domain(normalized)
    path = parsed.path.lower()

    if any(path.endswith(suffix) for suffix in BLOCKED_FILE_SUFFIXES):
        return True
    if domain in BLOCKED_DOMAINS:
        return True
    if any(domain.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS):
        return True
    if any(domain.endswith(suffix) for suffix in BLOCKED_DOMAIN_SUFFIXES):
        return True
    return False


def build_queries(keyword: str) -> list[str]:
    return [
        f"{keyword} manufacturer official website",
        f"{keyword} company contact email",
        f"{keyword} supplier official website",
        f"{keyword} exporter contact",
        f"{keyword} sales email company",
    ]


def search_candidates(keyword: str, limit: int = 10) -> list[dict]:
    config = load_config()
    api_key = config.get("SERPAPI_KEY")
    if not api_key:
        raise ValueError(".env 中缺少 SERPAPI_KEY")

    candidates = []
    seen_urls = set()
    per_query = max(10, min(limit, 20))

    for query in build_queries(keyword):
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": api_key,
                    "num": per_query,
                    "hl": "en",
                },
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            print(f"[搜索] 查询失败：{query} | {exc}")
            continue

        for item in data.get("organic_results", []):
            url = normalize_url(item.get("link", ""))
            if not url or url in seen_urls or is_blocked_url(url):
                continue
            seen_urls.add(url)
            candidates.append(
                {
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("snippet", ""),
                    "domain": get_domain(url),
                }
            )
            if len(candidates) >= limit:
                return candidates

    return candidates
