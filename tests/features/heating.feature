# language: en
Feature: Control heating using the associated Meter
  Each relay uses the temperature from its associated Meter.
  Heating turns on at or below 19.5 degrees Celsius.
  Heating turns off at or above 20 degrees Celsius.
  Between these limits, the relay keeps its previous state.

  Scenario Outline: Control heating with hysteresis
    Given a heating relay associated with a Meter
    And the relay is "<previous_state>"
    And the associated Meter has a valid temperature of <temperature> degrees Celsius
    When the heating engine evaluates the Meter reading
    Then the relay should be "<expected_state>"

    Examples:
      | temperature | previous_state | expected_state |
      | 19.4        | OFF            | ON             |
      | 19.5        | OFF            | ON             |
      | 19.6        | OFF            | OFF            |
      | 19.6        | ON             | ON             |
      | 19.9        | OFF            | OFF            |
      | 19.9        | ON             | ON             |
      | 20          | ON             | OFF            |
      | 20.1        | ON             | OFF            |

  Scenario Outline: Turn heating off when the Meter reading is unavailable
    Given a heating relay associated with a Meter
    And the relay is "ON"
    And the associated Meter reading is "<reading_status>"
    When the heating engine evaluates the Meter reading
    Then the relay should be "OFF"

    Examples:
      | reading_status |
      | MISSING        |
      | INVALID        |
      | STALE          |