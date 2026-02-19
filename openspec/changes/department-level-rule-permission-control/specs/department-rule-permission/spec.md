## ADDED Requirements

### Requirement: User can query department rules
The system SHALL allow users to query all rules within their department. Users MUST only see rules created by their department.

#### Scenario: User queries rules within their department
- **WHEN** user calls list_available_rules with valid auth_token
- **THEN** system returns all rules where department_id matches user's department_id

#### Scenario: User queries rules from different department
- **WHEN** user from department A tries to query rules from department B
- **THEN** system returns empty list or only public/company-visible rules


### Requirement: User can create rules
The system SHALL allow any logged-in user to create a new reconciliation rule. The system MUST automatically associate the rule with the user's department.

#### Scenario: User creates a new rule
- **WHEN** user calls save_rule with valid auth_token and rule data
- **THEN** system creates the rule and associates it with user's department_id
- **AND** system sets created_by to current user's user_id
- **AND** system sets visibility to "department" by default


### Requirement: Only creator can edit their rules
The system SHALL allow only the rule creator to edit their own rules. Other users MUST NOT be able to modify rules they did not create.

#### Scenario: Creator edits their own rule
- **WHEN** user who created the rule calls update_rule
- **THEN** system allows the update and saves changes

#### Scenario: Non-creator tries to edit rule
- **WHEN** user who is not the creator calls update_rule
- **THEN** system returns error: "无权修改该规则"


### Requirement: Only creator can delete their rules
The system SHALL allow only the rule creator to delete their own rules. Other users MUST NOT be able to delete rules they did not create.

#### Scenario: Creator deletes their own rule
- **WHEN** user who created the rule calls delete_rule
- **THEN** system deletes the rule

#### Scenario: Non-creator tries to delete rule
- **WHEN** user who is not the creator calls delete_rule
- **THEN** system returns error: "无权删除该规则"


### Requirement: User can only execute rules they have permission to use
The system SHALL verify user permissions before allowing rule execution. Users MUST have appropriate permissions to execute a reconciliation rule.

#### Scenario: User executes rule within their department
- **WHEN** user calls reconciliation_start with a rule belonging to their department
- **THEN** system allows the execution

#### Scenario: User tries to execute rule from different department
- **WHEN** user from department A tries to execute a rule from department B
- **THEN** system returns error: "无权使用该规则"


### Requirement: User can view rule details if they have permission
The system SHALL verify user permissions before returning rule details. Users MUST have appropriate permissions to view a reconciliation rule.

#### Scenario: User views rule details within their department
- **WHEN** user calls get_rule_detail with valid auth_token for a rule in their department
- **THEN** system returns the rule details

#### Scenario: User tries to view rule from different department
- **WHEN** user from department A tries to view a rule from department B
- **THEN** system returns error: "无权查看该规则"
