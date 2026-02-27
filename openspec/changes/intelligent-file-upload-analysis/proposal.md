## Why

The current file upload flow for reconciliation requires users to upload exactly 2 Excel files with standard format (header + data rows). This rigid approach fails to handle real-world scenarios where users have multi-sheet workbooks, single files needing sheet selection, or multiple files requiring intelligent pairing. Without intelligent analysis, users face manual trial-and-error, leading to errors and poor experience.

## What Changes

- Add pre-upload validation to detect standard 2-file format and route to existing flow
- Integrate LangGraph's `create_deep_agent` with skill system for intelligent file analysis
- Implement reconciliation rule matching validation when executing existing rules
- Add intelligent file pairing analysis for non-standard uploads (1 file multi-sheet, multi-file single-sheet, multi-file multi-sheet scenarios)
- Implement HITL (Human-In-The-Loop) workflow allowing users to review and adjust suggested file pairs
- Add data preview showing final selected data format before proceeding
- Pass confirmed header + data structure to downstream field mapping workflow

## Capabilities

### New Capabilities

- `file-format-validation`: Validates if uploaded files meet standard format (2 Excel files with header + data rows) and routes accordingly
- `deep-agent-file-analysis`: Uses LangGraph's `create_deep_agent` with skills to perform intelligent file analysis for non-standard scenarios
- `reconciliation-rule-matching`: Validates uploaded files match selected reconciliation rule requirements when executing existing rules
- `intelligent-file-pairing`: Analyzes uploaded files (multi-sheet, multi-file scenarios) and suggests optimal file/sheet pairs for reconciliation
- `hitl-file-confirmation`: Provides human-in-the-loop interface for users to review, adjust, and confirm suggested file pairs
- `data-preview-handoff`: Previews final selected data format and passes confirmed header + data structure to field mapping step

### Modified Capabilities

(None - this is entirely new functionality)

## Impact

**Affected Code**:
- File upload handling logic in reconciliation flow (`finance-agents/data-agent/`)
- Workflow routing to distinguish standard vs non-standard file uploads
- Field mapping input preparation

**New Dependencies**:
- LangGraph's `create_deep_agent` API integration
- Skill system for file analysis (new skill definition required)
- HITL framework for user interaction within agent workflow

**APIs**:
- File upload endpoint needs to route based on validation results
- New endpoints or state management for HITL interaction
- Data handoff interface to field mapping step

**User Experience**:
- New user prompts for file pairing confirmation
- Data preview display before proceeding
- Error messages for rule mismatch scenarios
