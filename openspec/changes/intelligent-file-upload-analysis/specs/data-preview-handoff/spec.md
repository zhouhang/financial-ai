## ADDED Requirements

### Requirement: Extract data from confirmed selections
The system SHALL extract header and data rows from user-confirmed file/sheet selections.

#### Scenario: Extract data from single-sheet files
- **WHEN** user confirms pair of single-sheet Excel files
- **THEN** system SHALL extract header row (first row) and all data rows from each file

#### Scenario: Extract data from specific sheets
- **WHEN** user confirms pair of sheets from multi-sheet file(s)
- **THEN** system SHALL extract header row and data rows only from the specified sheets

#### Scenario: Handle merged header cells
- **WHEN** confirmed sheet contains merged cells in header row
- **THEN** system SHALL unmerge and extract header values, duplicating merged value across columns as needed

### Requirement: Format data for field mapping compatibility
The system SHALL format extracted data to match existing field mapping input structure.

#### Scenario: Structure matches field mapping interface
- **WHEN** data extraction completes
- **THEN** output SHALL conform to structure: `{"file1": {"headers": [...], "data": [[...]]}, "file2": {"headers": [...], "data": [[...]]}}`

#### Scenario: Normalize data types
- **WHEN** extracted data contains mixed types (dates, numbers, strings)
- **THEN** system SHALL preserve original types but ensure JSON serializability (convert datetime to ISO strings)

#### Scenario: Handle empty cells
- **WHEN** extracted data contains empty cells
- **THEN** system SHALL represent empty cells as `null` in data array

### Requirement: Generate data preview for user
The system SHALL display preview of extracted data before proceeding to field mapping.

#### Scenario: Show first 10 rows of each dataset
- **WHEN** data extraction completes
- **THEN** system SHALL display first 10 rows (or all rows if fewer than 10) from each dataset with headers

#### Scenario: Show data statistics
- **WHEN** preview is displayed
- **THEN** system SHALL show total row counts for each dataset (e.g., "File 1: 1,523 rows, File 2: 1,498 rows")

#### Scenario: Highlight column types
- **WHEN** preview is displayed
- **THEN** system SHALL indicate detected data type for each column (e.g., "text", "number", "date")

### Requirement: Inform user about format persistence
The system SHALL communicate to user that this data format will be the expected format for future uploads.

#### Scenario: Display format guidance message
- **WHEN** data preview is shown
- **THEN** system SHALL display message: "Future uploads should match this format (same columns and data types) for this reconciliation rule"

#### Scenario: Provide example format
- **WHEN** user views preview
- **THEN** system SHALL offer option to download template files showing the expected format

### Requirement: Pass data to field mapping step
The system SHALL hand off extracted data structure to downstream field mapping workflow.

#### Scenario: Successful handoff to field mapping
- **WHEN** user confirms data preview
- **THEN** system SHALL invoke field mapping step with formatted data structure

#### Scenario: Include metadata in handoff
- **WHEN** handing off to field mapping
- **THEN** system SHALL include metadata: original file names, sheet names, extraction timestamp

### Requirement: Handle data quality issues
The system SHALL detect and warn about potential data quality issues before handoff.

#### Scenario: Warn about mismatched row counts
- **WHEN** two datasets have significantly different row counts (>20% difference)
- **THEN** system SHALL display warning but allow user to proceed if intentional

#### Scenario: Warn about missing critical columns
- **WHEN** dataset lacks columns commonly needed for reconciliation (e.g., ID, amount)
- **THEN** system SHALL display warning suggesting user verify column selection

#### Scenario: Detect duplicate headers
- **WHEN** dataset contains duplicate column names in header row
- **THEN** system SHALL display error and require user to fix headers before proceeding

### Requirement: Support data preview adjustment
The system SHALL allow user to return to file selection if preview reveals issues.

#### Scenario: User goes back to adjust selection
- **WHEN** user views data preview and notices incorrect sheet selected
- **THEN** system SHALL provide "Go Back" option to return to HITL confirmation and reselect

#### Scenario: User cancels and restarts
- **WHEN** user determines uploaded files are unsuitable after seeing preview
- **THEN** system SHALL provide "Start Over" option to return to file upload screen

### Requirement: Cache extracted data for performance
The system SHALL cache extracted data to avoid re-parsing if user navigates back and forth.

#### Scenario: Return from field mapping preserves data
- **WHEN** user proceeds to field mapping then navigates back to preview
- **THEN** system SHALL display same preview without re-extracting from files

#### Scenario: Cache expiration
- **WHEN** cached data is older than 1 hour
- **THEN** system SHALL re-extract data from original files to ensure freshness
