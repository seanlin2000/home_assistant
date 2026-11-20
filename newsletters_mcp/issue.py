"""One newsletter issue as saved on disk and read by the tools: its sections, each a title and its paragraphs in markdown."""

from datetime import datetime

from pydantic import BaseModel

from utils.text_utils import word_count


class Section(BaseModel):
    title: str
    paragraphs: list[str]  # plain text, "> " for a quotation, "- " for a list item, cells joined by " | " for a table row

    @property
    def words(self) -> int:
        return sum(word_count(paragraph) for paragraph in self.paragraphs)


class Issue(BaseModel):
    publication: str  # "Money Stuff", "The Morning", "WSJ Markets A.M."
    subject: str
    headline: str
    received: datetime  # when Gmail received it, in local time
    message_id: str
    sections: list[Section]

    @property
    def words(self) -> int:
        return sum(section.words for section in self.sections)
