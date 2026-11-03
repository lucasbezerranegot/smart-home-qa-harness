"""Common humidifier-provider adapter backed by a SwitchBot Plug Mini EU."""

from collections.abc import Callable
from dataclasses import dataclass

from smart_home_qa_harness.humidifier_provider import (
    HumidifierOperationState,
    HumidifierPowerCalibration,
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
    power_calibration: HumidifierPowerCalibration | None = None

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

        operation_state, operation_confirmed = _classify_operation(
            status.state,
            status.power,
            self.power_calibration,
        )
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
            operation_state=operation_state,
            operation_confirmed=operation_confirmed,
            operation_confirmation_supported=(
                self.power_calibration is not None
            ),
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


def _classify_operation(
    relay_state: PlugState,
    power_watts: float,
    calibration: HumidifierPowerCalibration | None,
) -> tuple[HumidifierOperationState | None, bool]:
    if calibration is None:
        return None, False
    if power_watts <= calibration.off_max_watts:
        return HumidifierOperationState.OFF, True
    if (
        relay_state is PlugState.ON
        and calibration.running_min_watts
        <= power_watts
        <= calibration.running_max_watts
    ):
        return HumidifierOperationState.RUNNING, True
    return HumidifierOperationState.AMBIGUOUS, False
