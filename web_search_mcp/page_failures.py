"""Why a page could not be read, so fetch_page can tell the model what to do next instead of saying only that it found no text.

Each cause carries the sentence the model reads. A bot check is told apart from a plain refusal by the header the filter adds, not by the status code:
AWS WAF answers 202 with `x-amzn-waf-action`, and Cloudflare answers 403 with `cf-mitigated: challenge`. Neither gives the page, and asking again
does not help, so the model should look elsewhere.
"""

from enum import StrEnum

import httpx


class PageFailure(StrEnum):
    BLOCKED_SITE = "the assistant does not read this site, which needs a login or keeps its pages behind a paywall; use another source"
    CHALLENGED = "the site answered with a bot check instead of the page; use another source"
    REFUSED = "the site refused the request (HTTP 403); use another source"
    NOT_FOUND = "the page does not exist at this address; search for where it moved"
    RATE_LIMITED = "the site is limiting requests (HTTP 429); use another source rather than asking again now"
    SITE_ERROR = "the site answered with an error; try again later or use another source"
    TIMED_OUT = "the site did not answer in time; try again or use another source"
    UNREACHABLE = "the site could not be reached; check the address or use another source"
    REDIRECT_LOOP = "the address redirects too many times"
    NOT_A_PAGE = "the address is a file or data, not a web page or text"
    TOO_LARGE = "the page is larger than the reader accepts; use another source"
    NO_TEXT = "the page has no readable text, perhaps because it builds its content in the browser; use another source"


class PageUnreadable(Exception):
    def __init__(self, failure: PageFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure

    @property
    def code(self) -> str:
        """The cause in one word, for logs and for the model to match on, e.g. "challenged"."""
        return self.failure.name.lower()


FAILURES_BY_STATUS = {403: PageFailure.REFUSED, 404: PageFailure.NOT_FOUND, 410: PageFailure.NOT_FOUND, 429: PageFailure.RATE_LIMITED}
READABLE_CONTENT_TYPES = ("html", "text/plain", "markdown")  # web pages, and the plain text and Markdown files such as a repository's README


def raise_if_unreadable(response: httpx.Response) -> None:
    """Raise PageUnreadable unless the response is a page or text to read. Called once redirects have been followed."""
    failure = failure_for(response)
    if failure is not None:
        raise PageUnreadable(failure)


def failure_for(response: httpx.Response) -> PageFailure | None:
    if is_bot_check(response):
        return PageFailure.CHALLENGED
    if response.is_error:
        return FAILURES_BY_STATUS.get(response.status_code, PageFailure.SITE_ERROR)
    if not any(kind in response.headers.get("content-type", "") for kind in READABLE_CONTENT_TYPES):
        return PageFailure.NOT_A_PAGE
    return None


def is_bot_check(response: httpx.Response) -> bool:
    return "x-amzn-waf-action" in response.headers or response.headers.get("cf-mitigated") == "challenge"


def failure_for_transport_error(error: httpx.HTTPError) -> PageFailure:
    return PageFailure.TIMED_OUT if isinstance(error, httpx.TimeoutException) else PageFailure.UNREACHABLE
