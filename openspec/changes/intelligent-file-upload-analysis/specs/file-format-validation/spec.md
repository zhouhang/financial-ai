## ADDED Requirements

### Requirement: Detect standard file format
The system SHALL validate if uploaded files meet the standard format of exactly 2 Excel files, each containing a single sheet with header row and data rows.

#### Scenario: Standard format detected
- **WHEN** user uploads exactly 2 Excel files, each with a single sheet containing header row and at least one data row
- **THEN** system SHALL mark upload as standard format and route to existing reconciliation flow

#### Scenario: Non-standard format - wrong file count
- **WHEN** user uploads 1 file or more than 2 files
- **THEN** system SHALL mark upload as non-standard format and route to intelligent analysis

#### Scenario: Non-standard format - multi-sheet file
- **WHEN** user uploads 2 Excel files where at least one file contains multiple sheets
- **THEN** system SHALL mark upload as non-standard format and route to intelligent analysis

#### Scenario: Non-standard format - no header row
- **WHEN** user uploads files where a sheet lacks a header row (first row contains only data types)
- **THEN** system SHALL mark upload as non-standard format and route to intelligent analysis

#### Scenario: Non-standard format - empty file
- **WHEN** user uploads files where a sheet is empty or contains only a header row without data
- **THEN** system SHALL mark upload as non-standard format and route to intelligent analysis

### Requirement: Route based on validation result
The system SHALL route the file upload to the appropriate processing path based on validation result.

#### Scenario: Route to existing flow
- **WHEN** upload is marked as standard format
- **THEN** system SHALL proceed directly to existing field mapping step without deep agent invocation

#### Scenario: Route to intelligent analysis
- **WHEN** upload is marked as non-standard format
- **THEN** system SHALL invoke deep agent with intelligent file analysis skill

### Requirement: Validation performance
The system SHALL complete file format validation within 2 seconds for files up to 10MB.

#### Scenario: Fast validation for standard uploads
- **WHEN** user uploads standard format files totaling 5MB
- **THEN** system SHALL complete validation and routing within 2 seconds
