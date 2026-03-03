## ADDED Requirements

### Requirement: Code refactoring preserves all existing functionality
The refactored code SHALL maintain exactly the same functionality as the original code.

#### Scenario: All helper functions work identically
- **WHEN** any helper function from the original helpers.py is called
- **THEN** the function SHALL return the same result as before the refactoring

#### Scenario: All node functions work identically  
- **WHEN** any node function from the original nodes.py is called
- **THEN** the node SHALL behave exactly as before the refactoring

### Requirement: Import compatibility maintained
The refactored modules SHALL maintain backward compatibility for all existing imports.

#### Scenario: Imports via __init__.py work
- **WHEN** code imports using `from app.graphs.reconciliation import func_name`
- **THEN** the import SHALL work without errors after refactoring

#### Scenario: Direct module imports work
- **WHEN** code imports using `from app.graphs.reconciliation.helpers import func_name`
- **THEN** the import SHALL work after moving functions to new modules

### Requirement: No functional changes to API
The refactoring SHALL NOT change any function signatures, return values, or side effects.

#### Scenario: Function signatures unchanged
- **WHEN** any function from the refactored modules is inspected
- **THEN** the function signature SHALL match the original

#### Scenario: Return values unchanged
- **WHEN** any function is called with the same arguments
- **THEN** the return value SHALL be identical to the original
