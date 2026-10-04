"""VeSync cloud adapter for a room's Levoit humidifier."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import math
from typing import Any, TypeVar

from aiohttp import ClientError
from pyvesync import VeSync
from pyvesync.const import ConnectionStatus, DeviceStatus
from pyvesync.utils.errors import (
    VeSyncAPIResponseError,
    VeSyncAPIStatusCodeError,
    VeSyncError,
    VeSyncLoginError,
    VeSyncRateLimitError,
    VeSyncServerError,
    VeSyncTokenError,
)

from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderError,
    HumidifierProviderStatus,
    HumidifierState,
)


_Result = TypeVar("_Result")


@dataclass(frozen=True)
class VeSyncHumidifierProvider:
    """Expose one VeSync humidifier through the common provider contract."""

    username: str
    password: str
    humidifier_device_id: str
    country_code: str
    time_zone: str
    timeout_seconds: float
    manager_factory: Callable[..., Any] = VeSync

    def __post_init__(self) -> None:
        for field_name, value in (
            ("username", self.username),
            ("password", self.password),
            ("humidifier_device_id", self.humidifier_device_id),
            ("country_code", self.country_code),
            ("time_zone", self.time_zone),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number.")
        if not callable(self.manager_factory):
            raise ValueError("manager_factory must be callable.")

    @property
    def provider_name(self) -> str:
        return "vesync"

    @property
    def device_id(self) -> str:
        return self.humidifier_device_id

    def read_status(self) -> HumidifierProviderStatus:
        return self._run(self._read_status())

    def set_state(self, state: HumidifierState) -> None:
        if not isinstance(state, HumidifierState):
            raise HumidifierProviderError(
                "INVALID_HUMIDIFIER_STATE",
                "Humidifier state must be ON or OFF.",
                False,
            )
        self._run(self._set_state(state))

    async def _read_status(self) -> HumidifierProviderStatus:
        async with self._new_manager() as manager:
            device = await self._resolve_device(manager)
            return HumidifierProviderStatus(
                provider_name=self.provider_name,
                device_id=self.device_id,
                reported_state=_common_state(device),
                state_confirmed=True,
                confirmation_supported=True,
            )

    async def _set_state(self, state: HumidifierState) -> None:
        async with self._new_manager() as manager:
            device = await self._resolve_device(manager)
            current_state = _common_state(device)
            if current_state is state:
                return

            accepted = (
                await device.turn_on()
                if state is HumidifierState.ON
                else await device.turn_off()
            )
            if accepted is not True:
                raise HumidifierProviderError(
                    "VESYNC_COMMAND_REJECTED",
                    "VeSync did not accept the humidifier power command.",
                    True,
                )

    def _new_manager(self):
        return self.manager_factory(
            username=self.username,
            password=self.password,
            country_code=self.country_code,
            time_zone=self.time_zone,
            redact=True,
        )

    async def _resolve_device(self, manager):
        logged_in = await manager.login()
        if logged_in is not True or not manager.enabled:
            raise HumidifierProviderError(
                "VESYNC_AUTHENTICATION_FAILED",
                "VeSync authentication failed.",
                False,
            )

        await manager.get_devices()
        matches = [
            device
            for device in manager.devices.humidifiers
            if device.cid == self.device_id
        ]
        if not matches:
            raise HumidifierProviderError(
                "VESYNC_HUMIDIFIER_NOT_FOUND",
                "The configured VeSync humidifier CID was not found.",
                False,
            )
        if len(matches) != 1:
            raise HumidifierProviderError(
                "VESYNC_HUMIDIFIER_AMBIGUOUS",
                "VeSync returned the configured humidifier CID more than once.",
                False,
            )

        device = matches[0]
        await device.update()
        connection_status = getattr(device.state, "connection_status", None)
        if connection_status is not ConnectionStatus.ONLINE:
            raise HumidifierProviderError(
                "VESYNC_HUMIDIFIER_OFFLINE",
                "The configured VeSync humidifier is not online.",
                True,
            )
        return device

    def _run(self, operation: Awaitable[_Result]) -> _Result:
        try:
            return asyncio.run(
                asyncio.wait_for(operation, timeout=self.timeout_seconds)
            )
        except HumidifierProviderError:
            raise
        except TimeoutError as error:
            raise HumidifierProviderError(
                "VESYNC_TIMEOUT",
                "VeSync did not respond before the timeout.",
                True,
            ) from error
        except (VeSyncLoginError, VeSyncTokenError) as error:
            raise HumidifierProviderError(
                "VESYNC_AUTHENTICATION_FAILED",
                "VeSync rejected the configured credentials.",
                False,
            ) from error
        except VeSyncRateLimitError as error:
            raise HumidifierProviderError(
                "VESYNC_RATE_LIMITED",
                "VeSync rate-limited the request.",
                True,
            ) from error
        except (VeSyncServerError, VeSyncAPIStatusCodeError) as error:
            raise HumidifierProviderError(
                "VESYNC_SERVER_ERROR",
                "VeSync returned a server error.",
                True,
            ) from error
        except VeSyncAPIResponseError as error:
            raise HumidifierProviderError(
                "VESYNC_INVALID_RESPONSE",
                "VeSync returned an invalid response.",
                False,
            ) from error
        except ClientError as error:
            raise HumidifierProviderError(
                "VESYNC_CONNECTION_ERROR",
                "The VeSync cloud could not be reached.",
                True,
            ) from error
        except VeSyncError as error:
            raise HumidifierProviderError(
                "VESYNC_PROVIDER_ERROR",
                "VeSync could not complete the operation.",
                False,
            ) from error


def _common_state(device) -> HumidifierState:
    device_status = getattr(device.state, "device_status", None)
    if device_status in (DeviceStatus.ON, DeviceStatus.RUNNING):
        return HumidifierState.ON
    if device_status in (
        DeviceStatus.OFF,
        DeviceStatus.PAUSED,
        DeviceStatus.STANDBY,
        DeviceStatus.IDLE,
    ):
        return HumidifierState.OFF
    raise HumidifierProviderError(
        "VESYNC_UNKNOWN_HUMIDIFIER_STATE",
        "VeSync returned an unknown humidifier power state.",
        False,
    )
