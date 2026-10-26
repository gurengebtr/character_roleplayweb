from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Phase(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default="", max_length=8000)


class CharacterInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    system_prompt: str = Field(min_length=1, max_length=20000)
    opening_message: str = Field(default="", max_length=4000)
    background: str = Field(default="", max_length=100000)
    phases: list[Phase] = Field(default_factory=list, max_length=20)
    memory_enabled: bool = True
    provider: Literal["chatgpt", "endpoint"] = "chatgpt"
    model: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def unique_phases(self):
        if len({p.id for p in self.phases}) != len(self.phases):
            raise ValueError("Phase IDs must be unique")
        return self


class ConversationInput(StrictModel):
    character_id: str
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class ConversationState(StrictModel):
    phase_id: str | None = None
    memory_note: str = Field(default="", max_length=4000)
    revision: int = Field(ge=1)


class TurnInput(StrictModel):
    content: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class EndpointInput(StrictModel):
    base_url: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=2000)


class LoginInput(StrictModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)
