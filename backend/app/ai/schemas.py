from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatAnswerOut(BaseModel):
    """What the model must return for a chat question (docs/ai-engineering.md, Chat answer)."""

    # The response format is a JSON schema the API enforces, which is why extra keys are refused.
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(max_length=4000)
    # Numbers of the sources the answer relies on, as shown in the prompt: [S1] is 1.
    cited_sources: list[int] = Field(max_length=20)
    grounded: bool


@dataclass(frozen=True)
class Turn:
    """One message sent to the model."""

    role: Literal["user", "assistant"]
    content: str
