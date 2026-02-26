## ADDED Requirements

### Requirement: Horizontal scroll support
The table SHALL support horizontal scrolling when content exceeds container width, maintaining fixed first column (filename) visible.

#### Scenario: Table overflow horizontally
- **WHEN** total column width exceeds container width
- **THEN** horizontal scrollbar appears and user can scroll to view hidden columns

#### Scenario: Fixed first column
- **WHEN** user scrolls horizontally
- **THEN** first column (filename) remains fixed while other columns scroll

### Requirement: Column visibility control
The system SHALL allow users to toggle visibility of each column, persisting preferences locally.

#### Scenario: Toggle column visibility
- **WHEN** user clicks column visibility toggle and selects/deselects a column
- **THEN** the column is shown/hidden immediately and preference is saved to localStorage

#### Scenario: Default columns visible
- **WHEN** user first loads the file analysis table
- **THEN** default set of columns are visible and others are hidden

### Requirement: View mode switching
The system SHALL provide three view modes: compact, standard, and expanded, affecting row height and content density.

#### Scenario: Switch to compact mode
- **WHEN** user selects compact view mode
- **THEN** table rows have minimal padding and only essential columns shown

#### Scenario: Switch to standard mode
- **WHEN** user selects standard view mode
- **THEN** table rows have normal padding and most columns visible

#### Scenario: Switch to expanded mode
- **WHEN** user selects expanded view mode
- **THEN** table rows have extra padding and all columns visible

### Requirement: Column width adjustment
The system SHALL allow users to drag column borders to resize column width.

#### Scenario: Resize column by dragging
- **WHEN** user drags column border handle
- **THEN** column width adjusts in real-time during drag

#### Scenario: Persist column width
- **WHEN** user adjusts column width
- **THEN** the width preference is saved to localStorage
