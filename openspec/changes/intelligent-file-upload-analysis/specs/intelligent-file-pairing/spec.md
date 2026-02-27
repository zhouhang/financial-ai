## ADDED Requirements

### Requirement: Detect single file scenario
The system SHALL detect when user uploads a single Excel file and prompt accordingly.

#### Scenario: Single file with single sheet
- **WHEN** user uploads 1 Excel file with 1 sheet for new rule creation
- **THEN** system SHALL prompt user indicating only one file was uploaded and reconciliation requires two data sources

#### Scenario: Single file with multiple sheets
- **WHEN** user uploads 1 Excel file with multiple sheets for new rule creation
- **THEN** system SHALL analyze sheets and suggest pairs of sheets within the file for reconciliation

### Requirement: Analyze multi-sheet files for pairing
The system SHALL analyze sheets within files to identify potential reconciliation pairs.

#### Scenario: Multi-sheet file with clear naming
- **WHEN** file contains sheets with names like "System A Data" and "System B Data"
- **THEN** system SHALL suggest these two sheets as a reconciliation pair with rationale based on naming

#### Scenario: Multi-sheet file with structural similarity
- **WHEN** file contains multiple sheets with similar column structures
- **THEN** system SHALL analyze column overlap and suggest sheet pairs with highest structural similarity

#### Scenario: Multi-sheet file with data characteristics
- **WHEN** file contains sheets with different data characteristics (row counts, value ranges)
- **THEN** system SHALL include data characteristics in pairing rationale (e.g., "Sheet1 has 1000 rows vs Sheet2 has 950 rows")

### Requirement: Analyze multi-file scenarios for pairing
The system SHALL analyze multiple uploaded files to suggest optimal file or file-sheet pairs.

#### Scenario: Multiple files with single sheets each
- **WHEN** user uploads 3+ Excel files each with single sheet
- **THEN** system SHALL suggest the most compatible file pair based on column overlap and naming similarity

#### Scenario: Multiple files with multiple sheets
- **WHEN** user uploads multiple files where each contains multiple sheets
- **THEN** system SHALL analyze all possible file-sheet combinations and suggest best pair across files

#### Scenario: File naming hints at pairing
- **WHEN** uploaded files have names like "bank_export.xlsx" and "erp_export.xlsx"
- **THEN** system SHALL use file names as context in pairing suggestions

### Requirement: Provide pairing rationale
The system SHALL include clear rationale for each suggested file/sheet pair.

#### Scenario: Rationale includes column overlap
- **WHEN** system suggests a pair
- **THEN** rationale SHALL include percentage of overlapping columns and list key shared columns

#### Scenario: Rationale includes naming similarity
- **WHEN** system suggests a pair based on names
- **THEN** rationale SHALL explain naming patterns that influenced the suggestion

#### Scenario: Rationale includes data characteristics
- **WHEN** system suggests a pair based on data analysis
- **THEN** rationale SHALL include relevant data characteristics (row counts, data types, value ranges)

### Requirement: Suggest multiple alternatives when ambiguous
The system SHALL provide multiple pairing options when no clear best match exists.

#### Scenario: Multiple equally viable pairs
- **WHEN** file analysis reveals 2+ pairs with similar compatibility scores
- **THEN** system SHALL present all viable pairs ranked by compatibility with separate rationales

#### Scenario: Low-confidence pairing
- **WHEN** all possible pairs have low compatibility scores (< 40% column overlap)
- **THEN** system SHALL warn user that files may not be suitable for reconciliation and still present best options

### Requirement: Handle edge cases gracefully
The system SHALL handle unusual file structures without failure.

#### Scenario: Sheets with no overlapping columns
- **WHEN** user uploads files where sheets have completely different column sets
- **THEN** system SHALL warn user about lack of overlap but still allow pairing with explicit user confirmation

#### Scenario: Very large number of sheets
- **WHEN** user uploads file(s) with 20+ sheets total
- **THEN** system SHALL limit analysis to sheets with data (skip empty sheets) and suggest top 3 pairs only

#### Scenario: Duplicate sheet names across files
- **WHEN** multiple files contain sheets with identical names
- **THEN** system SHALL disambiguate in suggestions using file name prefix (e.g., "file1:Sheet1" vs "file2:Sheet1")
