## ADDED Requirements

### Requirement: Validate files match rule schema
The system SHALL validate that uploaded files match the structural requirements of the selected reconciliation rule.

#### Scenario: Files match rule requirements
- **WHEN** user executes existing reconciliation rule and uploads files with columns matching rule schema
- **THEN** system SHALL return match result as true and proceed to data extraction

#### Scenario: Files missing required columns
- **WHEN** user uploads files missing columns required by selected rule schema
- **THEN** system SHALL return match result as false with error message listing missing columns

#### Scenario: Files have extra columns
- **WHEN** user uploads files with additional columns not in rule schema
- **THEN** system SHALL return match result as true (extra columns are acceptable) and proceed

#### Scenario: Column data types mismatch
- **WHEN** user uploads files where column data types differ from rule schema expectations
- **THEN** system SHALL return match result as false with error message indicating type mismatches

### Requirement: Compare file structure against rule definition
The system SHALL extract and compare file structure (columns, types) against reconciliation rule definition.

#### Scenario: Extract column metadata from uploaded files
- **WHEN** system validates files against rule
- **THEN** system SHALL extract column names, data types, and sample values from uploaded files

#### Scenario: Retrieve rule schema definition
- **WHEN** system validates files against rule
- **THEN** system SHALL load reconciliation rule schema including required columns and expected types

### Requirement: Provide clear mismatch error messages
The system SHALL generate user-friendly error messages when uploaded files don't match rule requirements.

#### Scenario: Missing columns error message
- **WHEN** validation fails due to missing columns
- **THEN** error message SHALL list each missing column name and indicate which file (file1/file2) is missing it

#### Scenario: Type mismatch error message
- **WHEN** validation fails due to data type mismatch
- **THEN** error message SHALL specify column name, expected type per rule, and actual detected type

#### Scenario: Multiple errors combined
- **WHEN** validation fails with multiple issues (missing columns and type mismatches)
- **THEN** error message SHALL list all issues in a structured format

### Requirement: Handle ambiguous rule schemas
The system SHALL handle cases where reconciliation rule schema is incomplete or ambiguous.

#### Scenario: Rule schema lacks column definitions
- **WHEN** reconciliation rule schema does not specify required columns
- **THEN** system SHALL skip structural validation and proceed with generic file pairing logic

#### Scenario: Rule schema uses flexible column matching
- **WHEN** reconciliation rule allows multiple column name variations (aliases)
- **THEN** system SHALL accept files if any alias matches
