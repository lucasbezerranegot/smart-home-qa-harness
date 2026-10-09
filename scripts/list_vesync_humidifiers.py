"""List VeSync humidifiers without exposing complete device identifiers."""

import asyncio
import json
import os

from pyvesync import VeSync


async def _list_humidifiers() -> dict:
    async with VeSync(
        username=os.environ["VESYNC_USERNAME"],
        password=os.environ["VESYNC_PASSWORD"],
        country_code=os.environ["VESYNC_COUNTRY_CODE"],
        time_zone=os.environ["VESYNC_TIME_ZONE"],
        redact=True,
    ) as manager:
        logged_in = await manager.login()
        await manager.get_devices()
        humidifiers = [
            {
                "name": getattr(device, "device_name", None),
                "model": getattr(device, "device_type", None),
                "cid_suffix": device.cid[-6:],
            }
            for device in manager.devices.humidifiers
        ]
    return {
        "logged_in": logged_in,
        "humidifier_count": len(humidifiers),
        "humidifiers": humidifiers,
    }


def main() -> int:
    print(json.dumps(asyncio.run(_list_humidifiers()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
