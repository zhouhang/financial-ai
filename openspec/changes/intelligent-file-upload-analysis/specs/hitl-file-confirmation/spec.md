## ADDED Requirements

### Requirement: Present suggestions to user for review
The system SHALL display file/sheet pairing suggestions to user with clear interface for review and adjustment.

#### Scenario: Display suggested pair with rationale
- **WHEN** agent generates pairing suggestions
- **THEN** system SHALL present suggestion to user including source references (file names, sheet names) and rationale

#### Scenario: Display multiple alternatives
- **WHEN** agent generates multiple pairing options
- **THEN** system SHALL display all options ranked by confidence score with individual rationales

#### Scenario: Show file preview
- **WHEN** user reviews suggestions
- **THEN** system SHALL provide preview of first 5 rows from each suggested sheet to help user assess suitability

### Requirement: Enable user to adjust selections
The system SHALL allow user to modify suggested pairings before confirmation.

#### Scenario: User selects different sheet from same file
- **WHEN** system suggests "File1:Sheet1" and "File1:Sheet2" but user prefers "File1:Sheet3"
- **THEN** system SHALL allow user to select "File1:Sheet3" from dropdown of available sheets

#### Scenario: User selects different file pair
- **WHEN** system suggests files A and B but user prefers files A and C
- **THEN** system SHALL allow user to change file selection from available uploaded files

#### Scenario: User swaps pair order
- **WHEN** system suggests "File1" as first dataset and "File2" as second dataset
- **THEN** system SHALL allow user to swap order (File2 first, File1 second) if desired

### Requirement: Validate user adjustments
The system SHALL validate that user-adjusted selections are valid before accepting.

#### Scenario: User selects same sheet twice
- **WHEN** user attempts to select the same sheet for both datasets in pair
- **THEN** system SHALL show validation error preventing selection of identical sources

#### Scenario: User selects empty sheet
- **WHEN** user attempts to select sheet with no data rows
- **THEN** system SHALL show validation warning but allow selection if user confirms

### Requirement: Support asynchronous confirmation
The system SHALL handle cases where user takes time to review before confirming.

#### Scenario: User confirms within session
- **WHEN** user reviews suggestions and confirms within 5 minutes
- **THEN** system SHALL immediately resume agent workflow with confirmed selections

#### Scenario: User returns to confirmation later
- **WHEN** user navigates away and returns to confirmation screen within 30 minutes
- **THEN** system SHALL restore HITL state from checkpointer and allow user to complete confirmation

#### Scenario: Confirmation times out
- **WHEN** user does not confirm within 30 minutes
- **THEN** system SHALL mark workflow as abandoned and require user to restart upload process

### Requirement: Capture user confirmation explicitly
The system SHALL require explicit user action to confirm pairing selections.

#### Scenario: User confirms suggested pair without changes
- **WHEN** user clicks "Confirm" button on suggested pair
- **THEN** system SHALL capture confirmation event and resume agent with original suggestions

#### Scenario: User confirms adjusted pair
- **WHEN** user modifies selections and clicks "Confirm"
- **THEN** system SHALL capture confirmation event with user's adjusted selections and resume agent

#### Scenario: User cancels workflow
- **WHEN** user clicks "Cancel" or "Start Over" button
- **THEN** system SHALL terminate agent workflow and return to file upload screen

### Requirement: Persist HITL state across requests
The system SHALL persist workflow state during HITL interruption to support async user interaction.

#### Scenario: Save interrupt state
- **WHEN** agent calls interrupt for HITL
- **THEN** system SHALL save agent state including suggestions, uploaded files, and workflow context to checkpointer

#### Scenario: Retrieve interrupt state on resume
- **WHEN** user submits confirmation
- **THEN** system SHALL retrieve agent state from checkpointer using thread_id and pass user input to agent

### Requirement: Provide clear UI affordances
The system SHALL design HITL interface to guide user through confirmation process.

#### Scenario: Highlight recommended option
- **WHEN** multiple pairing options are presented
- **THEN** system SHALL visually highlight the highest-ranked option as "Recommended"

#### Scenario: Show confidence indicators
- **WHEN** displaying pairing suggestions
- **THEN** system SHALL show confidence level (High/Medium/Low) based on column overlap percentage

#### Scenario: Provide help text
- **WHEN** user views HITL interface
- **THEN** system SHALL display help text explaining what reconciliation file pairs are and how to choose
