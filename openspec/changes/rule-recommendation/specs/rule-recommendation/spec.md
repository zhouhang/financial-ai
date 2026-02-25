## ADDED Requirements

### Requirement: Rule search by field mapping
The system SHALL search for matching rules based on field mapping hash when user completes field mapping configuration.

#### Scenario: Find matching rules
- **WHEN** user confirms field mapping with order_id, amount, and date fields for both business and finance sources
- **THEN** system SHALL compute a hash from the six field mapping values (business.order_id, business.amount, business.date, finance.order_id, finance.amount, finance.date)
- **AND** system SHALL query rules with matching field_mapping_hash
- **AND** system SHALL return up to 3 most relevant matching rules

#### Scenario: No matching rules found
- **WHEN** user confirms field mapping and no rules match the computed hash
- **THEN** system SHALL proceed to rule_config step to create a new rule
- **AND** system SHALL NOT display any recommendation prompt

### Requirement: Display recommended rules
The system SHALL display recommended rules with name and partial configuration info for user selection.

#### Scenario: Show rule recommendations
- **WHEN** matching rules are found
- **THEN** system SHALL display each rule's name
- **AND** system SHALL display partial configuration info (field_mapping_text, rule_config_text summary)
- **AND** system SHALL prompt user to select a rule or continue creating new rule

#### Scenario: User selects recommended rule
- **WHEN** user selects one of the recommended rules
- **THEN** system SHALL load the selected rule's full configuration
- **AND** system SHALL proceed to task_execution to perform reconciliation

#### Scenario: User declines recommendations
- **WHEN** user chooses to continue creating new rule
- **THEN** system SHALL proceed to rule_config step with current field mapping

### Requirement: Save rule after reconciliation
The system SHALL prompt user to save a copy of the recommended rule after reconciliation completes.

#### Scenario: Prompt to save rule
- **WHEN** reconciliation using recommended rule completes
- **THEN** system SHALL display reconciliation results
- **AND** system SHALL evaluate if the rule is suitable
- **AND** system SHALL prompt user whether to save the rule as their own

#### Scenario: User saves rule copy
- **WHEN** user inputs "保存"
- **THEN** system SHALL prompt user to input a new rule name
- **AND** system SHALL copy the rule with new name and current user as owner
- **AND** system SHALL confirm save success

#### Scenario: User declines to save
- **WHEN** user inputs "不要"
- **THEN** system SHALL return to field_mapping step
- **AND** system SHALL allow user to continue creating a new rule

### Requirement: Rule field mapping index
The system SHALL maintain a precomputed index for efficient rule matching.

#### Scenario: Compute hash for new rule
- **WHEN** a new rule is saved
- **THEN** system SHALL compute field_mapping_hash from the rule's field mappings
- **AND** system SHALL store the hash in the rule record

#### Scenario: Index existing rules
- **WHEN** database migration runs
- **THEN** system SHALL compute and populate field_mapping_hash for all existing rules
- **AND** system SHALL create database index on field_mapping_hash column

#### Scenario: Query performance
- **WHEN** system searches rules by field_mapping_hash
- **THEN** query SHALL complete in O(1) time complexity
- **AND** query SHALL support up to 100,000+ rules without performance degradation
