"""Your MenuMate pipeline goes here. Split it into more modules as you see fit."""
from schema import Output


def respond(conversation_id: str, history: list[dict], message: str) -> Output:
    """Return the assistant's output for the customer's latest message.

    history: earlier turns, each {"role": "user" | "assistant", "text": str}
    message: the customer's latest message
    """
    raise NotImplementedError("Build Parts 1-3 here.")
