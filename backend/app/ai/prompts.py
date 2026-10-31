from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.ai.schemas import Turn

PROMPT_DIRECTORY = Path(__file__).parent / "prompts"
# Recorded with every call. A prompt is never edited in place: a change is a new file and a new
# version, so a stored call always says which text it used (AGENTS.md).
CHAT_PROMPT_VERSION = "chat_answer.v1"


@dataclass(frozen=True)
class PromptSource:
    """One retrieved chunk as the model sees it."""

    number: int
    section_label: str | None
    heading: str | None
    content: str


@lru_cache
def load_prompt(version: str) -> str:
    return (PROMPT_DIRECTORY / f"{version}.md").read_text()


def escape_text(text: str) -> str:
    """Make < and > harmless, so text from a document or a user cannot close a tag we opened."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _escape_attribute(text: str) -> str:
    return escape_text(text).replace('"', "&quot;")


def build_chat_messages(
    question: str, sources: list[PromptSource], history: list[Turn]
) -> list[Turn]:
    """The one place a chat prompt is put together from document and user text.

    All of that text goes into the user turn, escaped and inside tags that the fixed system
    prompt declares to be data. None of it ever enters the system prompt.
    """
    source_blocks = []
    for source in sources:
        attributes = f'n="{source.number}"'
        if source.section_label:
            attributes += f' section="{_escape_attribute(source.section_label)}"'
        if source.heading:
            attributes += f' heading="{_escape_attribute(source.heading)}"'
        source_blocks.append(f"<source {attributes}>\n{escape_text(source.content)}\n</source>")
    parts = ["<sources>\n" + "\n".join(source_blocks) + "\n</sources>"]

    if history:
        turns = [f'<turn role="{turn.role}">{escape_text(turn.content)}</turn>' for turn in history]
        parts.append("<history>\n" + "\n".join(turns) + "\n</history>")

    parts.append(f"<question>\n{escape_text(question)}\n</question>")
    return [Turn(role="user", content="\n\n".join(parts))]
