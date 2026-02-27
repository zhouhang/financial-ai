## Context

The current reconciliation workflow in `finance-agents/data-agent/` expects users to upload exactly 2 Excel files with standard format (header row + data rows). The system immediately processes these files for field mapping and reconciliation execution.

Real-world usage reveals several unsupported scenarios:
- Users upload single Excel files with multiple sheets (each sheet is a different data source)
- Users upload multiple files where each contains multiple sheets
- Files don't match the selected reconciliation rule format when executing existing rules

Without intelligent analysis, users must manually extract/reorganize data before upload, leading to errors and abandonment.

**Current State**:
- File upload → immediate field mapping → reconciliation
- No validation against reconciliation rule requirements
- No support for sheet selection or file pairing

**Constraints**:
- Must preserve existing flow performance for standard uploads
- Must maintain existing field mapping interface (header + data structure)
- Must support async HITL workflow (user may take time to confirm)

## Goals / Non-Goals

**Goals:**
- Support non-standard file uploads (multi-sheet, multi-file scenarios)
- Provide intelligent suggestions for file/sheet pairing
- Validate uploaded files match reconciliation rule requirements
- Enable user review and adjustment of suggested pairings
- Preview final data format before proceeding to field mapping
- Route standard uploads directly to existing flow (no regression)

**Non-Goals:**
- Not modifying existing reconciliation algorithm or field mapping logic
- Not supporting non-Excel file formats (CSV, JSON, etc.) - Excel only
- Not automatic pairing without user confirmation (always require HITL)
- Not handling data transformation/cleaning (only selection/pairing)

## Decisions

### 1. Early Routing with Format Validation

**Decision**: Add upfront validation before agent invocation. If files meet standard format (exactly 2 Excel files, each with single sheet, standard header + data rows), route directly to existing flow.

**Rationale**:
- Preserves existing flow performance (no agent overhead for standard cases)
- Deep agent only invoked for complex scenarios requiring analysis
- Clear separation of concerns

**Alternatives Considered**:
- ❌ Always use deep agent: Adds unnecessary latency for 80% of uploads
- ❌ No validation, always route to agent: Wastes compute on simple cases

### 2. LangGraph Deep Agent with Skill System

**Decision**: Use LangGraph's `create_deep_agent` with a custom skill for file analysis.

**Rationale**:
- Skills provide modular, testable analysis logic separate from agent prompting
- `create_deep_agent` handles complex reasoning needed for file pairing
- Skills can be reused across multiple agent workflows if needed
- Built-in support for tool calling and structured outputs

**Implementation**:
```python
from langgraph.prebuilt import create_deep_agent

skill_path = "skills/intelligent-file-analyzer/"
agent = create_deep_agent(
    model=llm,
    tools=[],  # Skill provides tools via SKILL.md
    skill_path=skill_path,
    checkpointer=checkpointer  # For HITL state persistence
)
```

**Alternatives Considered**:
- ❌ Custom agent implementation: Reinvents wheel, LangGraph provides HITL/checkpointing
- ❌ Rule-based file pairing: Can't handle ambiguous cases or complex multi-sheet scenarios

### 3. Skill Design: intelligent-file-analyzer

**Decision**: Create single skill at `.claude/skills/intelligent-file-analyzer/` with two modes:

**Mode 1: Reconciliation Rule Matching** (executing existing rule)
- Input: uploaded files + selected reconciliation rule schema
- Output: validation result (match/mismatch) + error messages
- Logic: Compare file structure (columns, data types) against rule requirements

**Mode 2: Intelligent File Pairing** (creating new rule)
- Input: uploaded files (with sheets)
- Output: suggested file/sheet pairs for reconciliation
- Scenarios:
  - 1 file, 1 sheet → Prompt user "only uploaded one file"
  - 1 file, multiple sheets → Suggest pairs of sheets within file
  - Multiple files, single sheets → Suggest file pairs
  - Multiple files, multiple sheets → Analyze and suggest best pairs across files/sheets
- Use HITL: Present suggestions to user for adjustment

**Rationale**:
- Single skill keeps logic cohesive (all file analysis in one place)
- Two modes handle distinct use cases with shared analysis logic
- Skill system prompt guides agent behavior based on mode

**Alternatives Considered**:
- ❌ Two separate skills: Duplicates file parsing/analysis logic
- ❌ No skill, direct agent prompting: Harder to test, maintain, and reuse

### 4. HITL Integration with LangGraph Interrupts

**Decision**: Use LangGraph's built-in interrupt mechanism for user confirmation of file pairs.

**Implementation Flow**:
1. Agent analyzes files and generates suggestions
2. Agent calls `interrupt()` with suggestions payload
3. Frontend presents suggestions to user for review/adjustment
4. User confirms or modifies pairs
5. Agent resumes with confirmed pairs
6. Agent generates data preview

**Rationale**:
- Native LangGraph feature designed for HITL workflows
- Automatic state persistence via checkpointer
- Clean API for async user interactions

**State Management**:
- Use LangGraph's `MemorySaver` or persistent checkpointer
- Store thread_id in session/database for resuming later
- Handle timeout scenarios (user never responds)

**Alternatives Considered**:
- ❌ Custom callback system: Reinvents LangGraph's built-in HITL support
- ❌ Synchronous blocking: Poor UX, doesn't scale with async workflows

### 5. Data Structure Handoff to Field Mapping

**Decision**: Agent outputs standardized format matching existing field mapping input:
```python
{
    "file1": {"headers": [...], "data": [[...], [...]]},
    "file2": {"headers": [...], "data": [[...], [...]]}
}
```

**Rationale**:
- Keeps downstream field mapping interface unchanged (no refactoring required)
- Clear contract between file analysis and field mapping phases
- Data preview shows exactly what field mapping will receive

**Alternatives Considered**:
- ❌ Pass raw file paths: Field mapping would need to handle sheet selection
- ❌ New data format: Requires refactoring field mapping logic

### 6. Workflow Architecture

**Decision**: Add new router in main reconciliation graph:

```python
def route_file_upload(state):
    files = state["uploaded_files"]

    # Validation
    if is_standard_format(files):  # 2 files, single sheet each
        return "existing_flow"
    else:
        return "intelligent_analysis"

# Graph structure
graph = StateGraph(...)
graph.add_node("validate_files", validate_files_node)
graph.add_conditional_edges("validate_files", route_file_upload, {
    "existing_flow": "field_mapping",
    "intelligent_analysis": "deep_agent_analysis"
})
graph.add_node("deep_agent_analysis", run_deep_agent_with_skill)
graph.add_node("field_mapping", existing_field_mapping_node)
```

**Rationale**:
- Clean separation: validation → routing → analysis/existing flow
- Existing flow unchanged (just add conditional edge)
- Deep agent only invoked when needed

## Risks / Trade-offs

**[Risk] Deep agent adds latency for non-standard uploads**
- Mitigation: Early routing sends standard uploads directly to existing flow (no regression)
- Trade-off: Complex uploads take longer but provide better accuracy

**[Risk] Skill complexity for multi-sheet/multi-file pairing logic**
- Mitigation: Comprehensive test suite with all scenario combinations
- Mitigation: Clear skill documentation and examples in SKILL.md
- Trade-off: Initial development time higher but logic is reusable

**[Risk] HITL state management across async requests**
- Mitigation: Use LangGraph checkpointing for automatic state persistence
- Mitigation: Implement timeout handling (e.g., 30min limit for user response)
- Trade-off: Need to handle abandoned sessions (cleanup strategy)

**[Risk] File pairing suggestions may be incorrect**
- Mitigation: Always require user confirmation (never auto-proceed)
- Mitigation: Provide clear rationale in suggestions ("matched by column names...")
- Trade-off: Extra user step, but prevents data quality issues

**[Risk] Reconciliation rule schema may not be machine-readable**
- Mitigation: Ensure rule schema includes structured field definitions
- Mitigation: If schema unclear, fall back to asking user for clarification
- Trade-off: May require rule schema format standardization

**[Risk] Excel parsing failures (corrupted files, large files)**
- Mitigation: Add file size limits and validation before processing
- Mitigation: Clear error messages for parsing failures
- Trade-off: Some edge cases may not be supported

## Migration Plan

**Phase 1: Skill Development**
1. Create `.claude/skills/intelligent-file-analyzer/SKILL.md`
2. Implement file parsing and analysis logic
3. Add unit tests for all scenarios (1 file multi-sheet, multi-file, etc.)

**Phase 2: Deep Agent Integration**
1. Add `create_deep_agent` to reconciliation workflow
2. Implement file format validation and routing
3. Add HITL interrupt handling in frontend

**Phase 3: Testing & Rollout**
1. Test with real-world file examples
2. Gradual rollout: percentage-based feature flag
3. Monitor latency and error rates

**Rollback Strategy**:
- Feature flag to disable intelligent analysis (route all to existing flow)
- If issues detected, toggle flag to restore previous behavior
- No data migration needed (stateless processing)

## Open Questions

1. **Timeout Handling**: What should happen if user abandons HITL confirmation? Auto-cancel after 30min?
2. **Reconciliation Rule Schema Format**: Are existing rule schemas structured enough for automated matching? May need schema standardization.
3. **Large File Handling**: What's the file size limit? Should we chunk/stream large Excel files?
4. **Skill Tool Access**: Does skill need read access to reconciliation rule database, or pass rule as context?
