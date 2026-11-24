import logging
import re
from urllib.parse import quote_plus
import httpx

logger = logging.getLogger(__name__)


class WebResearchService:
    """
    Performs real-time web research and information lookup without hallucinating sources.
    Uses public search gateways and documentation APIs to extract verified citations.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    @classmethod
    def search(cls, query: str, max_results: int = 4) -> list[dict]:
        """
        Executes a web search query and returns verified citations.
        Returns: list of dicts with keys: 'title', 'url', 'snippet', 'domain'
        """
        query = query.strip()
        if not query:
            return []

        results = []

        # 1. Try DuckDuckGo Lite / HTML API
        try:
            results = cls._search_duckduckgo(query, max_results)
            if results:
                return results
        except Exception as e:
            logger.debug("DuckDuckGo search attempt failed: %s", e)

        # 2. Try Wikipedia Summary API for educational / technical concept definitions
        try:
            wiki_res = cls._search_wikipedia(query)
            if wiki_res:
                results.append(wiki_res)
                if len(results) >= max_results:
                    return results
        except Exception as e:
            logger.debug("Wikipedia fallback lookup failed: %s", e)

        # 3. Known Official Tech Docs Registry for programming & framework queries
        tech_docs = cls._match_tech_docs(query)
        if tech_docs:
            for doc in tech_docs:
                if not any(r["url"] == doc["url"] for r in results):
                    results.append(doc)
                if len(results) >= max_results:
                    break

        return results[:max_results]

    @classmethod
    def _search_duckduckgo(cls, query: str, max_results: int) -> list[dict]:
        encoded_query = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        with httpx.Client(timeout=6.0, follow_redirects=True, headers=cls.HEADERS) as client:
            resp = client.post("https://html.duckduckgo.com/html/", data={"q": query})
            if resp.status_code != 200:
                return []

            html = resp.text

            # Parse results from HTML using regex to avoid external dependency issues
            # DuckDuckGo HTML puts results inside <a class="result__snippet" ...> or <h2 class="result__title">
            results = []
            
            # Match result blocks
            link_pattern = re.compile(
                r'<a[^>]+class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL,
            )
            title_pattern = re.compile(
                r'<a[^>]+class="result__snippet"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL,
            )

            # DuckDuckGo standard title matching
            blocks = re.findall(
                r'<div class="result__body links_main.*?<h2[^>]*>.*?<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>',
                html,
                re.IGNORECASE | re.DOTALL,
            )

            for raw_url, raw_title, raw_snippet in blocks:
                clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
                
                # Unpack DDG uddg redirect url if needed
                actual_url = raw_url
                if "uddg=" in raw_url:
                    match = re.search(r"uddg=([^&]+)", raw_url)
                    if match:
                        from urllib.parse import unquote
                        actual_url = unquote(match.group(1))

                domain = actual_url.split("//")[-1].split("/")[0].replace("www.", "")

                if clean_title and actual_url.startswith("http"):
                    results.append({
                        "title": clean_title,
                        "url": actual_url,
                        "snippet": clean_snippet,
                        "domain": domain,
                    })

                if len(results) >= max_results:
                    break

            return results

    @classmethod
    def _search_wikipedia(cls, query: str) -> dict | None:
        """Looks up educational or technical concepts on Wikipedia."""
        search_term = quote_plus(query.split()[0] if len(query.split()) > 4 else query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term}"
        with httpx.Client(timeout=4.0, headers=cls.HEADERS) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("title") and data.get("extract"):
                    return {
                        "title": f"{data['title']} - Wikipedia",
                        "url": data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{data['title']}"),
                        "snippet": data["extract"][:300] + "...",
                        "domain": "en.wikipedia.org",
                    }
        return None

    @classmethod
    def _match_tech_docs(cls, query: str) -> list[dict]:
        """Provides verified official documentation citations for software engineering concepts."""
        q = query.lower()
        official_docs = [
            ("python", {
                "title": "Python 3 Documentation (Official)",
                "url": "https://docs.python.org/3/",
                "snippet": "Official documentation, language reference, and standard library documentation for Python 3.",
                "domain": "docs.python.org",
            }),
            ("django", {
                "title": "Django Project Documentation (Official)",
                "url": "https://docs.djangoproject.com/en/stable/",
                "snippet": "The web framework for perfectionists with deadlines. Official reference guides, tutorial, and API docs.",
                "domain": "docs.djangoproject.com",
            }),
            ("react", {
                "title": "React - The Library for Web and Native User Interfaces",
                "url": "https://react.dev/",
                "snippet": "Official React documentation, hooks reference, component lifecycles, and interactive examples.",
                "domain": "react.dev",
            }),
            ("fastapi", {
                "title": "FastAPI Framework Documentation",
                "url": "https://fastapi.tiangolo.com/",
                "snippet": "High-performance Python web framework for building modern APIs with standard Python type hints.",
                "domain": "fastapi.tiangolo.com",
            }),
            ("postgresql", {
                "title": "PostgreSQL Official Documentation",
                "url": "https://www.postgresql.org/docs/",
                "snippet": "PostgreSQL is a powerful, open-source object-relational database system.",
                "domain": "postgresql.org",
            }),
            ("javascript", {
                "title": "MDN Web Docs - JavaScript",
                "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
                "snippet": "Comprehensive reference and guides for JavaScript standards, syntax, and Web APIs from Mozilla.",
                "domain": "developer.mozilla.org",
            }),
            ("docker", {
                "title": "Docker Documentation & Guides",
                "url": "https://docs.docker.com/",
                "snippet": "Learn how to build, share, and run modern applications with Docker containers.",
                "domain": "docs.docker.com",
            }),
        ]

        matches = []
        for keyword, doc in official_docs:
            if keyword in q:
                matches.append(doc)

        return matches
