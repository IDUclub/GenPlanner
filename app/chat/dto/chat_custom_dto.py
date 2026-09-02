from pydantic import BaseModel, Field


class ChatCustomTurnDTO(BaseModel):
    """
    DTO for a single custom-territory (no scenario_id) chat turn.
    Attributes:
        user_query (str): The user's message for this turn.
        chat_id (str | None): Existing ChatStorage chat id; omit to start a new chat.
    """

    user_query: str = Field(min_length=1, examples=["Хочу жилую застройку на этой территории"])
    chat_id: str | None = Field(default=None, description="Existing chat id; omit to start a new chat")
