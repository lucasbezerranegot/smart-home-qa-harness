"""Common humidifier-provider adapter backed by a SwitchBot Plug Mini EU."""

from collections.abc import Callable
from dataclasses import dataclass

from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderError,
    HumidifierProviderStatus,
    HumidifierState,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentError,
)
from smart_home_qa_harness.switchbot_plug_client import (
    PlugState,
    SwitchBotPlugError,
    get_plug_status,
    set_plug_state,
)


@dataclass(frozen=True)
class SwitchBotPlugHumidifierProvider:
    token: str
    secret: str
    plug_device_id: str
    timestamp_ms: int
    nonce_factory: Callable[[], str]

    @property
    def provider_name(self) -> str:
        return "switchbot-plug"

    @property
    def device_id(self) -> str:
        return self.plug_device_id

    def read_status(self) -> HumidifierProviderStatus:
        try:
            status = get_plug_status(
                token=self.token,
                secret=self.secret,
                device_id=self.plug_device_id,
                timestamp_ms=self.timestamp_ms,
                nonce=self.nonce_factory(),
            )
        except (SwitchBotPlugError, IndoorEnvironmentError) as error:
            raise _translate_error(error) from error

        return HumidifierProviderStatus(
            provider_name=self.provider_name,
            device_id=status.device_id,
            reported_state=(
                HumidifierState.ON
                if status.state is PlugState.ON
                else HumidifierState.OFF
            ),
            state_confirmed=True,
            confirmation_supported=True,
            power_watts=status.power,
        )

    def set_state(self, state: HumidifierState) -> None:
        if not isinstance(state, HumidifierState):
            raise HumidifierProviderError(
                "INVALID_HUMIDIFIER_STATE",
                "Humidifier state must be ON or OFF.",
                False,
            )

        try:
            set_plug_state(
                token=self.token,
                secret=self.secret,
                device_id=self.plug_device_id,
                state=(
                    PlugState.ON
                    if state is HumidifierState.ON
                    else PlugState.OFF
                ),
                timestamp_ms=self.timestamp_ms,
                nonce=self.nonce_factory(),
            )
        except (SwitchBotPlugError, IndoorEnvironmentError) as error:
            raise _translate_error(error) from error


def _translate_error(
    error: SwitchBotPlugError | IndoorEnvironmentError,
) -> HumidifierProviderError:
    return HumidifierProviderError(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
    )
