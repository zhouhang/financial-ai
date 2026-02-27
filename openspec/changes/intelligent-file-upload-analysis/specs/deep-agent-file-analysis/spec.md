## ADDED Requirements

### Requirement: Initialize deep agent with skill
The system SHALL create a LangGraph deep agent instance with the intelligent file analyzer skill loaded.

#### Scenario: Deep agent initialization for reconciliation execution
- **WHEN** non-standard upload is detected and user is executing existing reconciliation rule
- **THEN** system SHALL initialize deep agent with skill path pointing to `intelligent-file-analyzer` skill and reconciliation rule context

#### Scenario: Deep agent initialization for new rule creation
- **WHEN** non-standard upload is detected and user is creating new reconciliation rule
- **THEN** system SHALL initialize deep agent with skill path pointing to `intelligent-file-analyzer` skill without rule context

### Requirement: Agent executes file analysis via skill
The system SHALL invoke the deep agent to analyze uploaded files using the intelligent file analyzer skill.

#### Scenario: Agent analyzes files for rule matching
- **WHEN** deep agent is invoked with reconciliation rule context
- **THEN** agent SHALL use skill to validate files match rule requirements and return validation result

#### Scenario: Agent analyzes files for pairing suggestions
- **WHEN** deep agent is invoked without rule context
- **THEN** agent SHALL use skill to analyze file/sheet structure and generate pairing suggestions

### Requirement: Skill provides structured output
The system SHALL ensure the deep agent skill returns structured output conforming to defined schemas.

#### Scenario: Rule matching output structure
- **WHEN** skill completes rule matching analysis
- **THEN** output SHALL include `match_result` (boolean), `error_messages` (array), and `file_details` (object)

#### Scenario: File pairing output structure
- **WHEN** skill completes file pairing analysis
- **THEN** output SHALL include `suggested_pairs` (array of pair objects), `rationale` (string), and `requires_hitl` (boolean)

### Requirement: Agent handles skill execution errors
The system SHALL gracefully handle errors during skill execution and provide meaningful feedback.

#### Scenario: Skill parsing error
- **WHEN** skill fails to parse uploaded Excel files (corrupted file, unsupported format)
- **THEN** system SHALL return error message to user indicating file parsing failure with specific error details

#### Scenario: Skill timeout
- **WHEN** skill execution exceeds 30 seconds
- **THEN** system SHALL terminate agent execution and return timeout error to user

### Requirement: Checkpointer enables resumable workflows
The system SHALL configure deep agent with checkpointer to support resumable HITL workflows.

#### Scenario: Save agent state before HITL
- **WHEN** agent reaches HITL interrupt point
- **THEN** system SHALL persist agent state using checkpointer with unique thread_id

#### Scenario: Resume agent after HITL
- **WHEN** user provides HITL confirmation
- **THEN** system SHALL restore agent state from checkpointer using thread_id and resume execution
