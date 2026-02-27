## 1. Skill Development

- [x] 1.1 Create `.claude/skills/intelligent-file-analyzer/` directory structure
- [x] 1.2 Write SKILL.md with system prompt for two modes (rule matching + file pairing)
- [x] 1.3 Implement Excel file parsing utility to extract sheets, headers, and data
- [ ] 1.4 Implement column analysis utility (overlap calculation, type detection)
- [ ] 1.5 Implement file/sheet pairing algorithm with scoring logic
- [ ] 1.6 Add unit tests for skill logic (multi-sheet, multi-file scenarios)

## 2. File Format Validation

- [x] 2.1 Create file format validation module in `finance-agents/data-agent/app/utils/`
- [x] 2.2 Implement `is_standard_format()` function to check 2 files, single sheet, header + data
- [x] 2.3 Add validation for header row detection (distinguish from data rows)
- [x] 2.4 Add validation for empty file/sheet detection
- [ ] 2.5 Add performance tests ensuring validation completes within 2 seconds for 10MB files

## 3. Deep Agent Integration

- [ ] 3.1 Add LangGraph dependency to `finance-agents/data-agent/pyproject.toml`
- [ ] 3.2 Create deep agent initialization module with `create_deep_agent` setup
- [ ] 3.3 Configure checkpointer (MemorySaver or persistent storage) for HITL state
- [ ] 3.4 Implement skill path loading mechanism (point to `.claude/skills/intelligent-file-analyzer/`)
- [ ] 3.5 Add error handling for skill execution failures (parsing errors, timeouts)
- [ ] 3.6 Implement 30-second timeout for skill execution

## 4. Workflow Routing

- [ ] 4.1 Locate main reconciliation graph in `finance-agents/data-agent/app/graphs/`
- [ ] 4.2 Add `validate_files` node to graph that runs format validation
- [ ] 4.3 Implement `route_file_upload()` conditional router function
- [ ] 4.4 Add conditional edge from `validate_files` to `existing_flow` or `intelligent_analysis`
- [ ] 4.5 Create `deep_agent_analysis` node that invokes deep agent
- [ ] 4.6 Ensure existing `field_mapping` node is reachable from both routes

## 5. Reconciliation Rule Matching

- [ ] 5.1 Create rule schema loading utility to fetch reconciliation rule definitions
- [ ] 5.2 Implement column comparison logic (required columns, data types)
- [ ] 5.3 Implement validation result formatting (match boolean, error messages array)
- [ ] 5.4 Add handling for missing required columns (generate clear error messages)
- [ ] 5.5 Add handling for data type mismatches (expected vs actual types)
- [ ] 5.6 Add fallback logic for ambiguous or incomplete rule schemas

## 6. Intelligent File Pairing

- [ ] 6.1 Implement single file detection and user prompt logic
- [ ] 6.2 Implement multi-sheet analysis within single file (naming, structure comparison)
- [ ] 6.3 Implement multi-file analysis (suggest file pairs based on compatibility)
- [ ] 6.4 Implement cross-file cross-sheet analysis for complex scenarios
- [ ] 6.5 Add rationale generation (column overlap %, naming similarity, data characteristics)
- [ ] 6.6 Implement alternative suggestions when ambiguous (rank by confidence score)
- [ ] 6.7 Add edge case handling (no column overlap, 20+ sheets, duplicate names)

## 7. HITL Workflow

- [ ] 7.1 Implement agent interrupt call with suggestions payload in skill
- [ ] 7.2 Create HITL state schema (thread_id, suggestions, user selections, timestamp)
- [ ] 7.3 Add backend endpoint to retrieve pending HITL requests by thread_id
- [ ] 7.4 Add backend endpoint to submit user confirmation and resume agent
- [ ] 7.5 Implement timeout handling (30-minute limit, auto-cancel abandoned workflows)
- [ ] 7.6 Add session cleanup logic for expired HITL states
- [ ] 7.7 Create frontend HITL confirmation UI component in `finance-web/src/components/`
- [ ] 7.8 Display suggestions with file/sheet names, rationale, and confidence indicators
- [ ] 7.9 Add file preview display (first 5 rows from each suggested sheet)
- [ ] 7.10 Implement user adjustment controls (dropdown for sheet selection, swap order button)
- [ ] 7.11 Add validation for user selections (prevent same sheet twice, warn on empty sheets)
- [ ] 7.12 Add "Confirm", "Cancel", and "Go Back" action buttons

## 8. Data Preview & Handoff

- [ ] 8.1 Implement data extraction from confirmed file/sheet selections
- [ ] 8.2 Add handling for merged header cells (unmerge and duplicate values)
- [ ] 8.3 Format extracted data to match field mapping input structure (headers + data arrays)
- [ ] 8.4 Normalize data types (convert datetime to ISO strings, handle null values)
- [ ] 8.5 Create data preview component in frontend showing first 10 rows
- [ ] 8.6 Display data statistics (total row counts, detected column types)
- [ ] 8.7 Add format persistence message and template file download option
- [ ] 8.8 Implement data quality warnings (mismatched row counts, duplicate headers, missing critical columns)
- [ ] 8.9 Add "Go Back" option to return to HITL selection
- [ ] 8.10 Implement data caching to avoid re-parsing on navigation (1-hour expiration)
- [ ] 8.11 Verify handoff to existing field mapping node with metadata (file names, sheet names, timestamp)

## 9. Testing

- [ ] 9.1 Create test dataset with all scenario combinations (1 file multi-sheet, multi-file, etc.)
- [ ] 9.2 Add integration test for standard format → existing flow routing
- [ ] 9.3 Add integration test for non-standard format → deep agent routing
- [ ] 9.4 Add test for rule matching validation (match and mismatch scenarios)
- [ ] 9.5 Add test for file pairing suggestions with different scenarios
- [ ] 9.6 Add test for HITL workflow (interrupt, user confirmation, resume)
- [ ] 9.7 Add test for data extraction and formatting
- [ ] 9.8 Add test for timeout handling (skill timeout, HITL timeout)
- [ ] 9.9 Add test for error scenarios (parsing failures, corrupted files)
- [ ] 9.10 Add performance test for validation speed (< 2 seconds for 10MB files)

## 10. Feature Flag & Rollout

- [ ] 10.1 Add feature flag configuration for intelligent file analysis
- [ ] 10.2 Implement feature flag check in routing logic (disable → route all to existing flow)
- [ ] 10.3 Add monitoring/logging for agent invocations, latency, and error rates
- [ ] 10.4 Create rollback plan documentation
- [ ] 10.5 Test feature flag toggle (enable/disable) without redeployment

## 11. Documentation

- [ ] 11.1 Document skill API and modes in SKILL.md
- [ ] 11.2 Add inline code comments for validation and routing logic
- [ ] 11.3 Document HITL workflow state management and checkpointer usage
- [ ] 11.4 Create user-facing help text for HITL confirmation UI
- [ ] 11.5 Document data structure contract between file analysis and field mapping
- [ ] 11.6 Add troubleshooting guide for common issues (parsing failures, rule mismatches)
