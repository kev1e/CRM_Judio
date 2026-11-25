"""An in-memory gateway for tests: records prompts instead of calling Telegram."""

from typing import ClassVar

from crm.telegram.gateway import LoginPrompt


class FakeGateway:
    sent: ClassVar[list[LoginPrompt]] = []
    # Set to an exception instance to make the next sends fail.
    failure: ClassVar[Exception | None] = None

    def send_login_prompt(self, prompt: LoginPrompt) -> int:
        if FakeGateway.failure is not None:
            raise FakeGateway.failure
        FakeGateway.sent.append(prompt)
        return 1000 + len(FakeGateway.sent)

    @classmethod
    def clear(cls) -> None:
        cls.sent = []
        cls.failure = None
