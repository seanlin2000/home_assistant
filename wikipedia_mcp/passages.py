"""The passage ranker moved to utils.passage_utils, where search_and_read shares it; this name stays so existing imports keep working."""

from utils.passage_utils import select_passages

__all__ = ["select_passages"]
