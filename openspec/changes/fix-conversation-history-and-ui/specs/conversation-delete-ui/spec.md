## ADDED Requirements

### Requirement: Delete button visibility on hover
The sidebar conversation list SHALL display a delete button when user hovers over a conversation item.

#### Scenario: Delete button appears on hover
- **WHEN** user hovers over a conversation item in the sidebar
- **THEN** a delete button (trash icon) SHALL appear on the right side of the item

#### Scenario: Delete button hidden when not hovering
- **WHEN** user moves mouse away from a conversation item
- **THEN** the delete button SHALL be hidden

### Requirement: Delete confirmation dialog
The system SHALL display a confirmation dialog before deleting a conversation.

#### Scenario: Confirmation dialog shown on delete click
- **WHEN** user clicks the delete button on a conversation
- **THEN** a confirmation dialog SHALL appear asking "确定要删除这个会话吗？"

#### Scenario: Cancel deletion
- **WHEN** user clicks "取消" in the confirmation dialog
- **THEN** the dialog SHALL close and the conversation SHALL remain unchanged

### Requirement: Delete conversation via API
The system SHALL call the DELETE API endpoint to remove the conversation from the server.

#### Scenario: Successful deletion
- **WHEN** user confirms deletion
- **THEN** the system SHALL call `DELETE /api/conversations/{id}` with the auth token
- **AND** on success, the conversation SHALL be removed from the sidebar list
- **AND** if the deleted conversation was active, the system SHALL switch to another conversation

#### Scenario: Delete active conversation
- **WHEN** user deletes the currently active conversation
- **THEN** the system SHALL automatically select another conversation (first in list, or create new if list is empty)

#### Scenario: API failure handling
- **WHEN** the DELETE API returns an error
- **THEN** the conversation SHALL remain in the list
- **AND** an error message SHALL be logged to console

### Requirement: Server conversations sync after deletion
After deleting a conversation, the local state SHALL be updated without requiring a full reload.

#### Scenario: Local state update
- **WHEN** deletion succeeds
- **THEN** the conversation SHALL be removed from `serverConversations` state
- **AND** the sidebar SHALL re-render without the deleted conversation
