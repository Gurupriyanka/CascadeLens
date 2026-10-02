from smolagents import Model
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)


def _tool_call(call_id: str, name: str, arguments: dict) -> ChatMessage:
    """Build a model reply that asks the agent to call one tool."""
    return ChatMessage(
        role=MessageRole.ASSISTANT,
        content=None,
        tool_calls=[
            ChatMessageToolCall(
                id=call_id,
                type="function",
                function=ChatMessageToolCallFunction(name=name, arguments=arguments),
            )
        ],
    )


class FakeModel(Model):
    """A model with no AI: it replays two hand-written replies, one per step."""

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.step = 0

    def generate(self, messages, stop_sequences=None, response_format=None,
                 tools_to_call_from=None, **kwargs) -> ChatMessage:
        self.step += 1
        if self.step == 1:
            return _tool_call("call_1", "get_pipeline_statuses", {"db_path": self.db_path})
        return _tool_call("call_2", "final_answer", {"answer": "fake run finished"})