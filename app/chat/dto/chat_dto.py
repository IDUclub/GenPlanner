from pydantic import BaseModel, Field


class ChatTurnDTO(BaseModel):
    """
    DTO for a single chat turn.
    Attributes:
        user_query (str): The user's message for this turn.
        chat_id (str | None): Existing ChatStorage chat id; omit to start a new chat.
        test (bool): Route generation through the test Urban API, same as the DTO field on
            GenPlannerFuncZonesDTO -- project_id/scenario_id still come from the URL/session,
            never from chat text.
    """

    user_query: str = Field(min_length=1, examples=["Хочу 50% жильё, 30% бизнес и 20% рекреации"])
    chat_id: str | None = Field(default=None, description="Existing chat id; omit to start a new chat")
    test: bool = Field(default=False, description="Route generation through the test Urban API")
