# language: en
Feature: Respect ventilation periods

  Scenario Outline: Allow ventilation only during configured periods
    Given the daily maximum temperature is 20 degrees Celsius
    And the relative humidity is 65 percent
    And the current time is "<time>"
    And the outside temperature is 18 degrees Celsius
    And the inside temperature is 22 degrees Celsius
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

  Scenario Outline: Use humidity as the ventilation trigger on cool days
    Given the daily maximum temperature is 20 degrees Celsius
    And the relative humidity is <humidity> percent
    And the current time is "08:00:00"
    And the outside temperature is 18 degrees Celsius
    And the inside temperature is 22 degrees Celsius
    When the engine evaluates ventilation
    Then the action should be "<action>"

    Examples:
      | humidity | action       |
      | 59.9     | NO_ACTION    |
      | 60       | OPEN_WINDOWS |
      | 60.1     | OPEN_WINDOWS |

  Scenario Outline: Switch ventilation rules at the warm-day threshold
    Given the daily maximum temperature is <temperature> degrees Celsius
    And the relative humidity is 65 percent
    And the current time is "08:00:00"
    And the outside temperature is 18 degrees Celsius
    And the inside temperature is 22 degrees Celsius
    When the engine evaluates ventilation
    Then the action should be "<action>"

    Examples:
      | temperature | action       |
      | 23.9        | OPEN_WINDOWS |
      | 24          | NO_ACTION    |
      | 24.1        | NO_ACTION    |

  Scenario Outline: Use environmental temperature as the ventilation trigger on warm mornings
    Given the daily maximum temperature is 30 degrees Celsius
    And the relative humidity is 65 percent
    And the current time is "08:00:00"
    And the outside temperature is <outside_temperature> degrees Celsius
    And the inside temperature is <inside_temperature> degrees Celsius
    When the engine evaluates ventilation
    Then the action should be "<action>"

    Examples:
      | outside_temperature | inside_temperature | action        |
      | 18                  | 22                 | NO_ACTION     |
      | 23.9                | 25                 | NO_ACTION     |
      | 24                  | 25                 | CLOSE_WINDOWS |
      | 24.1                | 25                 | CLOSE_WINDOWS |
      | 23                  | 22                 | CLOSE_WINDOWS |
      | 23                  | 23                 | CLOSE_WINDOWS |

  Scenario Outline: Use environmental temperature as the ventilation trigger on warm evenings
    Given the daily maximum temperature is 30 degrees Celsius
    And the relative humidity is 65 percent
    And the current time is "20:00:00"
    And the outside temperature is <outside_temperature> degrees Celsius
    And the inside temperature is <inside_temperature> degrees Celsius
    When the engine evaluates ventilation
    Then the action should be "<action>"

    Examples:
      | outside_temperature | inside_temperature | action        |
      | 28                  | 25                 | NO_ACTION     |
      | 22                  | 23.9               | NO_ACTION     |
      | 22                  | 24                 | NO_ACTION     |
      | 24                  | 24                 | NO_ACTION     |
      | 25                  | 25                 | NO_ACTION     |
      | 22                  | 25                 | OPEN_WINDOWS  |