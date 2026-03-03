## ADDED Requirements

### Requirement: Login loads most recent conversation
When a user successfully logs in, the system SHALL load the most recent conversation from their history instead of creating a new conversation.

#### Scenario: User has conversation history
- **WHEN** user logs in with existing conversations in the server
- **THEN** the system SHALL load the most recent conversation (first in the list ordered by updated_at DESC)
- **AND** the conversation messages SHALL be displayed in the chat area
- **AND** no new conversation SHALL be created

#### Scenario: User has no conversation history
- **WHEN** user logs in with no existing conversations
- **THEN** the system SHALL create a new conversation
- **AND** the new conversation SHALL be set as the active conversation

### Requirement: Login does not create redundant conversation
The system SHALL NOT create a new conversation when loading conversation history during login.

#### Scenario: Race condition prevented
- **WHEN** user logs in and conversation list is being loaded
- **THEN** the system SHALL wait for the loading to complete
- **AND** only after the list is loaded, the system SHALL decide whether to load an existing conversation or create a new one

#### Scenario: Prevent premature new conversation creation
- **WHEN** user logs in but conversation list has not been fetched yet
- **THEN** the system SHALL NOT create a new conversation
- **AND** the system SHALL wait for loadConversations to complete first
