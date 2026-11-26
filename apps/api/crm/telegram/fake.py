"""An in-memory gateway for tests: records messages instead of calling Telegram."""

from typing import ClassVar

from crm.telegram.gateway import LoginPrompt, TaskMessage


class FakeGateway:
    sent: ClassVar[list[LoginPrompt]] = []
    messages: ClassVar[list[TaskMessage]] = []
    # Set to an exception instance to make the next sends fail.
    failure: ClassVar[Exception | None] = None

    def send_login_prompt(self, prompt: LoginPrompt) -> int:
        if FakeGateway.failure is not None:
            raise FakeGateway.failure
        FakeGateway.sent.append(prompt)
        return 1000 + len(FakeGateway.sent)

    def send_task_message(self, message: TaskMessage) -> int:
        if FakeGateway.failure is not None:
            raise FakeGateway.failure
        FakeGateway.messages.append(message)
        return 2000 + len(FakeGateway.messages)

    @classmethod
    def clear(cls) -> None:
        cls.sent = []
        cls.messages = []
        cls.failure = None
