import re
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from search import get_domain, normalize_url


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

LINK_KEYWORDS = [
    "contact",
    "contact-us",
    "about",
    "about-us",
    "support",
    "team",
    "company",
    "sales",
    "inquiry",
    "customer",
    "partner",
    "문의",
    "연락",
    "회사소개",
    "お問い合わせ",
    "会社概要",
]

BAD_EMAIL_PARTS = [
    "noreply",
    "no-reply",
    "example.com",
    "yourdomain.com",
    "test@",
    "privacy@",
    "legal@",
    "dpo@",
    "abuse@",
    "webmaster@",
    "postmaster@",
    "careers@",
    "hr@",
    "jobs@",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def clean_url(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    return urlunparse(parsed._replace(fragment="", query=""))


def is_valid_email(email: str) -> bool:
    value = email.strip().lower().strip(".,;:()[]{}<>\"'")
    if not EMAIL_RE.fullmatch(value):
        return False
    if any(part in value for part in BAD_EMAIL_PARTS):
        return False
    return True


def extract_emails(text: str) -> list[str]:
    emails = []
    seen = set()
    for raw in EMAIL_RE.findall(text or ""):
        email = raw.strip().lower().strip(".,;:()[]{}<>\"'")
        if is_valid_email(email) and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


def extract_mailto_emails(soup: BeautifulSoup) -> list[str]:
    emails = []
    seen = set()
    for tag in soup.select("a[href^='mailto:']"):
        href = tag.get("href", "")
        email = href.split("mailto:", 1)[-1].split("?", 1)[0].strip()
        email = unescape(email).lower()
        if is_valid_email(email) and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


def page_text_from_soup(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def should_follow_link(url: str, base_domain: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    full = url.lower()
    if get_domain(url) != base_domain:
        return False
    return any(keyword.lower() in full or keyword.lower() in path for keyword in LINK_KEYWORDS)


def fetch_page(url: str) -> tuple[str, str]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(f"Unsupported content type: {content_type}")
    return response.url, response.text


def parse_page(url: str, html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = page_text_from_soup(soup)
    return {
        "url": url,
        "title": title,
        "text": text[:3000],
        "html": html[:5000],
        "mailto_emails": extract_mailto_emails(soup),
        "regex_emails": extract_emails(text),
    }


def collect_priority_links(base_url: str, html: str, base_domain: str, max_links: int) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    seen = set()
    for tag in soup.select("a[href]"):
        href = tag.get("href", "").strip()
        if not href or href.startswith(("javascript:", "tel:", "#")):
            continue
        absolute = clean_url(urljoin(base_url, href))
        if absolute in seen or not should_follow_link(absolute, base_domain):
            continue
        seen.add(absolute)
        links.append(absolute)
        if len(links) >= max_links:
            break
    return links


def crawl_candidate(url: str, max_pages: int = 5) -> dict:
    start_url = clean_url(url)
    base_domain = get_domain(start_url)
    result = {
        "url": start_url,
        "final_url": start_url,
        "title": "",
        "pages": [],
        "candidate_emails": [],
        "links": [],
        "error": "",
    }

    try:
        final_url, html = fetch_page(start_url)
        final_url = clean_url(final_url)
        result["final_url"] = final_url
        base_domain = get_domain(final_url)
        first_page = parse_page(final_url, html)
        result["title"] = first_page["title"]
        result["pages"].append(first_page)
        priority_links = collect_priority_links(final_url, html, base_domain, max_pages - 1)
        result["links"] = priority_links
    except Exception as exc:
        result["error"] = str(exc)
        return result

    visited = {result["final_url"]}
    for link in result["links"]:
        if len(result["pages"]) >= max_pages or link in visited:
            continue
        visited.add(link)
        try:
            final_url, html = fetch_page(link)
            final_url = clean_url(final_url)
            if get_domain(final_url) != base_domain:
                continue
            result["pages"].append(parse_page(final_url, html))
        except Exception as exc:
            print(f"[Crawler] Page skipped: {link} | {exc}")

    seen_emails = set()
    all_text_len = 0
    for page in result["pages"]:
        all_text_len += len(page.get("text", ""))
        if all_text_len > 12000:
            page["text"] = page.get("text", "")[: max(0, 12000 - (all_text_len - len(page.get("text", ""))))]
        for email in page.get("mailto_emails", []) + page.get("regex_emails", []):
            if email not in seen_emails:
                seen_emails.add(email)
                result["candidate_emails"].append(email)

    return result

