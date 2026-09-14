# language: en
Feature: Respect ventilation periods

  Scenario Outline: Allow ventilation only during configured periods
    Given the daily maximum temperature is 20 degrees Celsius
    And the relative humidity is 65 percent
    And the current time is "<time>"
    When the engine evaluates ventilation
    Then the action should be "<action>"

    Examples:
      | time     | action       |
      | 05:59:59 | NO_ACTION    |
      | 06:00:00 | OPEN_WINDOWS |
      | 11:00:00 | OPEN_WINDOWS |
      | 11:00:01 | NO_ACTION    |
      | 17:59:59 | NO_ACTION    |
      | 18:00:00 | OPEN_WINDOWS |
      | 23:00:00 | OPEN_WINDOWS |
      | 23:00:01 | NO_ACTION    |
