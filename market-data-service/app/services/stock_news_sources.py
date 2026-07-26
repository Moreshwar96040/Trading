"""Multi-source per-stock news: don't let one provider decide whether a stock
has news.

Why this exists: yfinance's news endpoint returns nothing for a large share of
NSE tickers (and breaks whenever Yahoo reshuffles its internal API). A sentiment
engine fed by one fragile source is a sentiment engine that mostly says "no
data". So we fan out across several keyless RSS sources and merge:

    GoogleNews  keyword search, India edition — carries PTI/Reuters/ET/Mint/
                Moneycontrol/BusinessLine syndication; the broadest single net
    BingNews    keyword search — different index, catches what Google misses
    YahooRSS    Yahoo's own per-symbol headline feed (separate from the API
                yfinance uses, so it survives that endpoint breaking)

All are free, need no API key, and are env-configurable (STOCK_NEWS_FEEDS) so a
source can be swapped without touching code.

The hard part is precision, not recall. A keyword search for "Bajaj Finance"
happily returns Bajaj Auto and Bajaj Housing stories, and feeding those to the
sentiment model would produce confidently wrong scores. `is_relevant` is the
gate: a headline must clearly name the company (or its ticker) to be stored.
Everything here except `fetch_stock_feeds` is pure and unit-tested offline.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

MAX_PER_FEED = 12
#: Words that carry no identifying signal in an Indian listed-company name.
_NOISE_TOKENS = {
    "ltd", "ltd.", "limited", "plc", "inc", "inc.", "corp", "corp.", "corporation",
    "company", "co", "co.", "the", "of", "and", "&", "india", "indian", "group",
    "holdings", "holding", "enterprises", "ventures", "&co",
}
#: Match on a prefix, not the whole token: headlines shorten "Pharmaceutical"
#: to "Pharma", "Industries" to "Inds". Four chars keeps "Finance"/"Financial"
#: together while still separating "Bajaj Finance" from "Bajaj Auto".
_PREFIX_LEN = 4
#: A company whose short name reduces to one token (e.g. "Infosys") is matched
#: on that token alone; two-token names require both.
_MAX_TOKENS_CHECKED = 2


def company_tokens(name: str) -> list[str]:
    """Distinctive lowercase tokens of a company name, noise words removed.

    >>> company_tokens("Bajaj Finance Ltd")
    ['bajaj', 'finance']
    >>> company_tokens("Sun Pharmaceutical Industries Limited")
    ['sun', 'pharmaceutical', 'industries']
    """
    raw = re.split(r"[^\w&]+", (name or "").lower())
    return [t for t in raw if t and t not in _NOISE_TOKENS and not t.isdigit()]


def search_query(ticker: str, name: str) -> str:
    """Search expression for the keyword feeds: the company's short name as a
    phrase, OR its ticker. Quoting the phrase is what keeps Google from
    returning every story containing either word separately."""
    tokens = company_tokens(name)[:_MAX_TOKENS_CHECKED]
    phrase = " ".join(tokens)
    if phrase and ticker:
        return f'"{phrase}" OR "{ticker}"'
    return f'"{phrase}"' if phrase else f'"{ticker}"'


def is_relevant(title: str, ticker: str, name: str) -> bool:
    """Does this headline actually name the company?

    Accepts an exact ticker mention, or the company's leading name tokens
    appearing as a *consecutive* phrase (prefix-matched, so abbreviations
    survive). Adjacency is what separates a company from its siblings —
    "Bajaj Housing Finance" contains both "bajaj" and "finance" but is a
    different listed entity, so a scattered match must not count.

    >>> is_relevant("Bajaj Auto Q1 profit rises 12%", "BAJFINANCE", "Bajaj Finance Ltd")
    False
    >>> is_relevant("Bajaj Housing Finance IPO opens", "BAJFINANCE", "Bajaj Finance Ltd")
    False
    >>> is_relevant("Sun Pharma gets USFDA nod", "SUNPHARMA", "Sun Pharmaceutical Industries")
    True
    """
    haystack = (title or "").lower()
    if not haystack:
        return False

    title_tokens = [t for t in re.split(r"[^\w]+", haystack) if t]
    if ticker and ticker.lower() in title_tokens:
        return True

    needles = [n[:_PREFIX_LEN] for n in company_tokens(name)[:_MAX_TOKENS_CHECKED]]
    if not needles:
        return False
    span = len(needles)
    for start in range(len(title_tokens) - span + 1):
        if all(title_tokens[start + offset].startswith(needle)
               for offset, needle in enumerate(needles)):
            return True
    return False


def title_key(title: str) -> str:
    """Stable identity for a headline, so the same story arriving from Google,
    Bing and Yahoo is stored once. Punctuation and spacing are normalized
    because syndicated copies differ in exactly those ways."""
    normalized = re.sub(r"[^\w\s]", "", (title or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode()).hexdigest()[:32]


def build_feed_urls(feed_config: str, ticker: str, name: str,
                    yahoo_symbol: str) -> list[tuple[str, str]]:
    """"Name|url-template" CSV -> [(source, url)], placeholders substituted.

    Templates may use {query} (URL-encoded search expression) and {symbol}
    (the Yahoo symbol, e.g. BAJFINANCE.NS)."""
    query = quote_plus(search_query(ticker, name))
    out: list[tuple[str, str]] = []
    for entry in (feed_config or "").split(","):
        if "|" not in entry:
            continue
        source, template = entry.split("|", 1)
        source, template = source.strip(), template.strip()
        if not source or not template:
            continue
        out.append((source, template.replace("{query}", query)
                                    .replace("{symbol}", yahoo_symbol or ticker)))
    return out


def normalize_items(items: list[dict], source: str, ticker: str, name: str,
                    max_age_days: int) -> list[dict]:
    """Parsed feed items -> news_articles rows: relevance-filtered, recency-
    filtered, and keyed by title so cross-source duplicates collapse."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    rows: list[dict] = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or not is_relevant(title, ticker, name):
            continue
        published = item.get("published_at")
        if published is not None:
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < cutoff:
                continue
        rows.append({
            "external_id": title_key(title),
            "title": title[:500],
            # Google/Bing wrap the real outlet in the title as " - Mint"; the
            # feed's own name is the honest fallback.
            "publisher": (_outlet_from_title(title) or source)[:120],
            "link": (item.get("link") or None) and str(item["link"])[:1000],
            "published_at": published,
        })
    return rows


def _outlet_from_title(title: str) -> str | None:
    """Google News titles end with " - Publisher"; recover it for display."""
    if " - " not in title:
        return None
    tail = title.rsplit(" - ", 1)[1].strip()
    return tail if 0 < len(tail) <= 60 else None


def fetch_stock_feeds(ticker: str, name: str, yahoo_symbol: str, feed_config: str,
                      max_age_days: int = 21,
                      errors: list | None = None) -> list[dict]:
    """Fan out across the configured feeds and return merged, deduped rows.
    Network-facing and fully best-effort: one dead source never sinks the rest,
    and a total failure returns [] with reasons appended to `errors`."""
    import httpx

    from app.services.market_news_service import parse_feed

    merged: dict[str, dict] = {}
    for source, url in build_feed_urls(feed_config, ticker, name, yahoo_symbol):
        try:
            resp = httpx.get(url, timeout=10.0, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                if errors is not None:
                    errors.append(f"{source}: HTTP {resp.status_code}")
                continue
            items = parse_feed(resp.text, source)[:MAX_PER_FEED]
        except Exception as exc:                  # noqa: BLE001 — one bad feed ≠ no news
            log.warning("Stock feed %s failed for %s: %s", source, ticker, exc)
            if errors is not None:
                errors.append(f"{source}: {exc}")
            continue
        for row in normalize_items(items, source, ticker, name, max_age_days):
            merged.setdefault(row["external_id"], row)   # first source wins
    return sorted(merged.values(),
                  key=lambda r: (r["published_at"] is not None, r["published_at"]
                                 or datetime.min.replace(tzinfo=timezone.utc)),
                  reverse=True)
