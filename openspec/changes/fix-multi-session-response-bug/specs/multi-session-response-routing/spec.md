## ADDED Requirements

### Requirement: Response routing to correct session
AI response messages SHALL be routed to the session where the user sent the original message, regardless of session changes that occur after the message is sent.

#### Scenario: Response after creating new session
- **WHEN** user sends a message in session A, then immediately creates a new session B
- **THEN** the AI response SHALL appear in session A (the original session where the message was sent)

#### Scenario: Response after switching to existing session
- **WHEN** user sends a message in session A, then switches to session B
- **THEN** the AI response SHALL appear in session A (the original session where the message was sent)

#### Scenario: Response in same session (no switch)
- **WHEN** user sends a message in session A and does not switch sessions
- **THEN** the AI response SHALL appear in session A

### Requirement: Request context preservation
The system SHALL preserve the target session ID at the time a message is sent, using it for routing the corresponding response.

#### Scenario: Message send captures session context
- **WHEN** user sends a message in session A
- **THEN** the system SHALL record session A as the target for the response

#### Scenario: Multiple sequential messages
- **WHEN** user sends message 1 in session A (response pending), then sends message 2 in session A
- **THEN** response to message 1 SHALL appear in session A and response to message 2 SHALL appear in session A

### Requirement: Loading state management
The system SHALL correctly manage the loading state when creating new sessions, without prematurely clearing in-progress request status.

#### Scenario: Creating new session during active request
- **WHEN** user has an active AI request (isLoading=true) and creates a new session
- **THEN** the isLoading state SHALL remain true for the original session until the response is received
