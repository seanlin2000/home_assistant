"""The browser user agent sent by the tools that read pages made for people (the search server's page reader and the listings refreshes): a personal
assistant reading what one person would, not a crawler."""

# Exactly what current Chrome on a Mac sends: Chrome freezes the macOS version at 10_15_7 and zeroes the minor version numbers, so any other form marks
# the request as not a real browser. Keep the major version current; sites turn away browsers a few versions old.
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
