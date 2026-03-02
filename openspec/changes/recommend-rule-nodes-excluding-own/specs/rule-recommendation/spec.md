## ADDED Requirements

### Requirement: Logged-in user recommendations exclude own rules
When a user is logged in, the rule recommendation system SHALL NOT recommend rules that the current user has created.

#### Scenario: Logged-in user gets recommendations
- **WHEN** a logged-in user requests rule recommendations
- **THEN** the system SHALL exclude rules where `created_by` matches the current user's ID

### Requirement: Guest user recommendations include all matching rules
When a guest user (not logged in) requests rule recommendations, the system SHALL return all matching rules without filtering.

#### Scenario: Guest user gets recommendations
- **WHEN** a guest user requests rule recommendations
- **THEN** the system SHALL return all rules matching the search criteria

### Requirement: Recommendation filtering applies to hash-based search
The hash-based search path (`search_rules_by_mapping`) SHALL apply the same filtering logic as the field name matching path.

#### Scenario: Hash search filters current user's rules
- **WHEN** a logged-in user triggers hash-based rule search
- **THEN** the results SHALL NOT include rules created by the current user
