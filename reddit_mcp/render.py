"""The tool's text: each thread's subreddit, month, votes, and title, the start of its post, and its top comments, one per line so the word budget
cuts between comments rather than inside one."""

import re
from datetime import UTC, datetime

from reddit_mcp.arctic_shift import RedditPost
from reddit_mcp.settings import RedditSettings
from reddit_mcp.threads import RedditQuery, RedditThread
from utils.text_utils import clip_to_whole_lines, clip_to_words, word_count

# Arctic Shift reads a post's votes and comment count again about 36 hours after it is posted; before that both read 0 or 1.
VOTES_SETTLE_SECONDS = 36 * 3600
MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BARE_URL = re.compile(r"https?://\S+")
OLD_THREADS_NOTE = "These are opinions from people on Reddit. Say how old a thread is when it is more than a year old, since places and prices change."


def threads_text(threads: list[RedditThread], reddit_query: RedditQuery, settings: RedditSettings, now: float) -> str:
    """The threads within the word budget, cut between lines, with the note on old threads always kept at the end."""
    header = f'Reddit threads for "{reddit_query.query}" {where(reddit_query.subreddits)}, most relevant first.'
    body = "\n".join([header, *(line for index, thread in enumerate(threads, start=1) for line in thread_lines(index, thread, settings, now))])
    return f"{clip_to_whole_lines(body, settings.max_words - word_count(OLD_THREADS_NOTE))}\n{OLD_THREADS_NOTE}"


def where(subreddits: list[str]) -> str:
    return "in " + " and ".join(f"r/{subreddit}" for subreddit in subreddits) if subreddits else "across Reddit"


def thread_lines(index: int, thread: RedditThread, settings: RedditSettings, now: float) -> list[str]:
    post_text = plain(thread.post.selftext)
    post_line = [f"    Post: {clip_to_words(post_text, settings.words_per_post)}"] if post_text else []
    comment_lines = [f"    Comment ({comment.score} upvotes): {clip_to_words(plain(comment.body), settings.words_per_comment)}" for comment in thread.comments]
    return [f"[{index}] {thread_heading(thread.post, now)}", *post_line, *(comment_lines or ["    No comments could be read."])]


def thread_heading(post: RedditPost, now: float) -> str:
    posted = datetime.fromtimestamp(post.created_utc, tz=UTC)
    votes = "votes not counted yet" if now - post.created_utc < VOTES_SETTLE_SECONDS else f"{post.score} upvotes, {post.num_comments} comments"
    return f"r/{post.subreddit}, {posted:%B} {posted.year}, {votes}: {plain(post.title)}"


def plain(markdown: str) -> str:
    """Reddit's markdown as speakable text on one line: a link keeps its words, a bare address is dropped."""
    return " ".join(BARE_URL.sub("", MARKDOWN_LINK.sub(r"\1", markdown)).split())
