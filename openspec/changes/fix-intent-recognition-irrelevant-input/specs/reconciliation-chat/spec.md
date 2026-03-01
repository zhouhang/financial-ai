## MODIFIED Requirements

### Requirement: Intent recognition for irrelevant user input
The system SHALL recognize user intent when users input irrelevant content (like "不要", casual chat, etc.) during any reconciliation workflow stage.

#### Scenario: Guest user inputs irrelevant content
- **WHEN** guest user inputs irrelevant content during any workflow stage
- **THEN** system classifies intent and responds appropriately (CANCEL/OTHER/RESUME_WORKFLOW)

#### Scenario: Logged-in user inputs irrelevant content
- **WHEN** logged-in user inputs irrelevant content during any workflow stage
- **THEN** system classifies intent and responds appropriately

#### Scenario: User says "不要" during rule recommendation
- **WHEN** user inputs "不要" during rule recommendation phase
- **THEN** system recognizes CANCEL intent and returns to field mapping with proper message

### Requirement: Consistent handling across all workflow nodes
All reconciliation workflow nodes SHALL have consistent intent recognition logic for both guest and logged-in modes.

#### Scenario: Intent check in file_analysis_node
- **WHEN** user provides input after interrupt in file_analysis_node
- **THEN** system checks intent (RESUME_WORKFLOW vs other) and handles appropriately

#### Scenario: Intent check in rule_config_node
- **WHEN** user provides input after interrupt in rule_config_node
- **THEN** system checks intent and handles appropriately for both guest and logged-in modes

#### Scenario: Intent check in validation_preview_node
- **WHEN** user provides input after interrupt in validation_preview_node
- **THEN** system checks intent and handles appropriately
