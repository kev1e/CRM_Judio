"""Who performs an operation.

Every state-changing domain service receives an Actor, so authorization and audit
never have to guess. Only a `user` actor can hold permissions; `system` and `cli`
actors are used by dedicated internal flows that enforce their own preconditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crm.identity.models import User


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    CLI = "cli"


@dataclass(frozen=True, slots=True)
class Actor:
    type: ActorType
    user: User | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if (self.type is ActorType.USER) != (self.user is not None):
            raise ValueError("A user actor needs a user; other actors must not have one.")
        if self.type is not ActorType.USER and not self.label:
            raise ValueError("System and CLI actors need a label.")

    @classmethod
    def for_user(cls, user: User) -> Actor:
        return cls(type=ActorType.USER, user=user)

    @classmethod
    def system(cls, component: str) -> Actor:
        return cls(type=ActorType.SYSTEM, label=component)

    @classmethod
    def cli(cls, operator: str) -> Actor:
        return cls(type=ActorType.CLI, label=operator)
