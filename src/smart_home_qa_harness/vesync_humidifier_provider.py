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


class VeSyncCycleSession:
    """Share one VeSync login and device inventory within one app cycle."""

    def __init__(
        self,
        *,
        username: str,
        password: str,
        country_code: str,
        time_zone: str,
        timeout_seconds: float,
        manager_factory: Callable[..., Any] = VeSync,
    ):
        self.username = username
        self.password = password
        self.country_code = country_code
        self.time_zone = time_zone
        self.timeout_seconds = timeout_seconds
        self.manager_factory = manager_factory
        self._runner: asyncio.Runner | None = None
        self._manager_context = None
        self._manager = None
        self._initialized = False
        self._initialization_error: HumidifierProviderError | None = None

    def __enter__(self):
        if self._runner is not None:
            raise RuntimeError("VeSync cycle session is already open.")
        self._initialization_error = None
        self._runner = asyncio.Runner()
        return self

    def __exit__(self, exception_type, exception, traceback):
        runner = self._runner
        if runner is None:
            return False
        try:
            if self._manager_context is not None and self._manager is not None:
                runner.run(
                    self._manager_context.__aexit__(
                        exception_type, exception, traceback
                    )
                )
        finally:
            runner.close()
            self._runner = None
            self._manager_context = None
            self._manager = None
            self._initialized = False
        return False

    def read_status(self, device_id: str) -> HumidifierProviderStatus:
        device = self._run(self._resolve_device(device_id))
        return HumidifierProviderStatus(
            provider_name="vesync",
            device_id=device_id,
            reported_state=_common_state(device),
            state_confirmed=True,
            confirmation_supported=True,
        )

    def set_state(self, device_id: str, state: HumidifierState) -> None:
        self._run(self._set_state(device_id, state))

    async def _set_state(
        self, device_id: str, state: HumidifierState
    ) -> None:
        device = await self._resolve_device(device_id)
        if _common_state(device) is state:
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

    async def _resolve_device(self, device_id: str):
        manager = await self._ensure_manager()
        matches = [
            device
            for device in manager.devices.humidifiers
            if device.cid == device_id
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
        connection_status = getattr(
            device.state, "connection_status", None
        )
        if connection_status is not ConnectionStatus.ONLINE:
            raise HumidifierProviderError(
                "VESYNC_HUMIDIFIER_OFFLINE",
                "The configured VeSync humidifier is not online.",
                True,
            )
        return device

    async def _ensure_manager(self):
        if self._initialization_error is not None:
            raise self._initialization_error
        if self._manager is not None and self._initialized:
            return self._manager
        try:
            context = self.manager_factory(
                username=self.username,
                password=self.password,
                country_code=self.country_code,
                time_zone=self.time_zone,
                redact=True,
            )
            manager = await context.__aenter__()
            self._manager_context = context
            self._manager = manager
            logged_in = await manager.login()
            if logged_in is not True or not manager.enabled:
                raise HumidifierProviderError(
                    "VESYNC_AUTHENTICATION_FAILED",
                    "VeSync authentication failed.",
                    False,
                )
            await manager.get_devices()
            self._initialized = True
            return manager
        except Exception as error:
            translated = _translate_vesync_error(error)
            self._initialization_error = translated
            raise translated from error

    def _run(self, operation: Awaitable[_Result]) -> _Result:
        if self._runner is None:
            raise RuntimeError("VeSync cycle session is not open.")
        try:
            return self._runner.run(
                asyncio.wait_for(operation, timeout=self.timeout_seconds)
            )
        except Exception as error:
            translated = _translate_vesync_error(error)
            if self._manager is not None and not self._initialized:
                self._initialization_error = translated
            raise translated from error


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
    cycle_session: VeSyncCycleSession | None = None

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
        if self.cycle_session is not None:
            return self.cycle_session.read_status(self.device_id)
        with self._new_cycle_session() as session:
            return session.read_status(self.device_id)

    def set_state(self, state: HumidifierState) -> None:
        if not isinstance(state, HumidifierState):
            raise HumidifierProviderError(
                "INVALID_HUMIDIFIER_STATE",
                "Humidifier state must be ON or OFF.",
                False,
            )
        if self.cycle_session is not None:
            self.cycle_session.set_state(self.device_id, state)
            return
        with self._new_cycle_session() as session:
            session.set_state(self.device_id, state)

    def _new_cycle_session(self) -> VeSyncCycleSession:
        return VeSyncCycleSession(
            username=self.username,
            password=self.password,
            country_code=self.country_code,
            time_zone=self.time_zone,
            timeout_seconds=self.timeout_seconds,
            manager_factory=self.manager_factory,
        )


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


def _translate_vesync_error(error: Exception) -> HumidifierProviderError:
    if isinstance(error, HumidifierProviderError):
        return error
    if isinstance(error, TimeoutError):
        return HumidifierProviderError(
            "VESYNC_TIMEOUT",
            "VeSync did not respond before the timeout.",
            True,
        )
    if isinstance(error, (VeSyncLoginError, VeSyncTokenError)):
        return HumidifierProviderError(
            "VESYNC_AUTHENTICATION_FAILED",
            "VeSync rejected the configured credentials.",
            False,
        )
    if isinstance(error, VeSyncRateLimitError):
        return HumidifierProviderError(
            "VESYNC_RATE_LIMITED",
            "VeSync rate-limited the request.",
            True,
        )
    if isinstance(error, (VeSyncServerError, VeSyncAPIStatusCodeError)):
        return HumidifierProviderError(
            "VESYNC_SERVER_ERROR",
            "VeSync returned a server error.",
            True,
        )
    if isinstance(error, VeSyncAPIResponseError):
        return HumidifierProviderError(
            "VESYNC_INVALID_RESPONSE",
            "VeSync returned an invalid response.",
            False,
        )
    if isinstance(error, ClientError):
        return HumidifierProviderError(
            "VESYNC_CONNECTION_ERROR",
            "The VeSync cloud could not be reached.",
            True,
        )
    if isinstance(error, VeSyncError):
        return HumidifierProviderError(
            "VESYNC_PROVIDER_ERROR",
            "VeSync could not complete the operation.",
            False,
        )
    raise error
