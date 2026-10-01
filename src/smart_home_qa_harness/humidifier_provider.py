"""Provider-neutral contract for controlling room humidifiers."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class HumidifierState(Enum):
    OFF = "OFF"
    ON = "ON"


@dataclass(frozen=True)
class HumidifierProviderStatus:
    """State reported by a provider, with explicit physical confidence."""

    provider_name: str
    device_id: str
    reported_state: HumidifierState | None
    state_confirmed: bool
    confirmation_supported: bool = True
    power_watts: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_name, str) or not self.provider_name.strip():
            raise ValueError("provider_name must be a non-empty string.")
        if not isinstance(self.device_id, str) or not self.device_id.strip():
            raise ValueError("device_id must be a non-empty string.")
        if self.reported_state is not None and not isinstance(
            self.reported_state,
            HumidifierState,
        ):
            raise ValueError("reported_state must be a HumidifierState or None.")
        if not isinstance(self.state_confirmed, bool):
            raise ValueError("state_confirmed must be a boolean.")
        if not isinstance(self.confirmation_supported, bool):
            raise ValueError("confirmation_supported must be a boolean.")
        if self.state_confirmed and not self.confirmation_supported:
            raise ValueError("An unsupported confirmation cannot be confirmed.")
        if self.state_confirmed and self.reported_state is None:
            raise ValueError("A confirmed status requires a reported state.")


class HumidifierProviderError(Exception):
    """Structured error shared by every humidifier provider adapter."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@runtime_checkable
class HumidifierProvider(Protocol):
    """Small contract consumed by the room-level humidifier controller."""

    @property
    def provider_name(self) -> str: ...

    @property
    def device_id(self) -> str: ...

    def read_status(self) -> HumidifierProviderStatus: ...

    def set_state(self, state: HumidifierState) -> None: ...
