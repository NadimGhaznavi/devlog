from dataclasses import dataclass


@dataclass(frozen=True)
class Repository:
    identity: str

    @property
    def name(self) -> str:
        return self.identity.removeprefix("github.com/")
