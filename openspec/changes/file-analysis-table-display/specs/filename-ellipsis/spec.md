## ADDED Requirements

### Requirement: Filename truncation
The system SHALL truncate long filenames with ellipsis when they exceed specified character limit.

#### Scenario: Truncate long filename
- **WHEN** filename length exceeds 30 characters
- **THEN** filename is truncated to 27 characters with "..." appended

#### Scenario: Display full filename in tooltip
- **WHEN** user hovers over truncated filename
- **THEN** tooltip displays the complete filename without truncation

### Requirement: Configurable truncation limit
The system SHALL allow configurable character limit for filename truncation.

#### Scenario: Custom truncation length
- **WHEN** user sets custom truncation length in settings
- **THEN** filenames are truncated to the specified length

#### Scenario: Disable truncation
- **WHEN** user sets truncation length to 0 or maximum
- **THEN** filenames display in full without truncation
