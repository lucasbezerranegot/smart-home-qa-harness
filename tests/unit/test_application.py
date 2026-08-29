import pytest
from smart_home_qa_harness.application import (
    ApplicationConfig,
    ConfigurationError,
    load_application_config,
)

VALID_ENVIRON = {
    "WEATHER_LATITUDE": "48.13",
    "WEATHER_LONGITUDE": "11.57",
    "SWITCHBOT_TOKEN": "fake-switchbot-token",
    "SWITCHBOT_SECRET": "fake-switchbot-secret",
    "SWITCHBOT_DEVICE_ID": "AABBCCDDEEFF",
    "VOICE_MONKEY_API_TOKEN": "fake-voice-monkey-token",
    "VOICE_MONKEY_OPEN_DEVICE_ID": "fake-open-device",
    "VOICE_MONKEY_CLOSE_DEVICE_ID": "fake-close-device",
}

def test_load_application_config_returns_valid_config():

    result = load_application_config(VALID_ENVIRON)

    assert result == ApplicationConfig(
        latitude=48.13,
        longitude=11.57,
        switchbot_token="fake-switchbot-token",
        switchbot_secret="fake-switchbot-secret",
        switchbot_device_id="AABBCCDDEEFF",
        voice_monkey_api_token="fake-voice-monkey-token",
        voice_monkey_open_device_id="fake-open-device",
        voice_monkey_close_device_id="fake-close-device",
    )

@pytest.mark.parametrize(
    "missing_key",
    list(VALID_ENVIRON.keys()),
)
def test_load_application_config_rejects_missing_variable(missing_key):
    environ = VALID_ENVIRON.copy()
    del environ[missing_key]

    with pytest.raises(ConfigurationError) as captured:
        load_application_config(environ)

    assert captured.value.code == "MISSING_CONFIGURATION"
    assert captured.value.retryable is False
    assert missing_key in captured.value.message

@pytest.mark.parametrize(
    "key",
    [
        "WEATHER_LATITUDE",
        "WEATHER_LONGITUDE",
    ],
)
def test_load_application_config_rejects_non_numeric_coordinate(key):
    environ = VALID_ENVIRON.copy()
    environ[key] = "not-a-number"

    with pytest.raises(ConfigurationError) as captured:
        load_application_config(environ)

    assert captured.value.code == "INVALID_CONFIGURATION"
    assert captured.value.retryable is False
    assert captured.value.message
