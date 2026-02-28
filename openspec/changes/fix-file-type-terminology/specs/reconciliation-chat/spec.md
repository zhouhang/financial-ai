## MODIFIED Requirements

### Requirement: Reconciliation chat terminology
The reconciliation chat system SHALL use generic file terminology ("文件1/文件2") instead of business-specific terms ("业务文件/财务文件") in all user-facing output.

#### Scenario: File upload prompt
- **WHEN** user starts a reconciliation conversation
- **THEN** system prompts "请上传两个文件进行对账" instead of "请上传业务文件和财务文件"

#### Scenario: File reference in conversation
- **WHEN** system refers to uploaded files in conversation
- **THEN** system uses "文件1" and "文件2" instead of "业务数据" or "财务数据"

#### Scenario: Reconciliation result display
- **WHEN** system displays reconciliation results
- **THEN** results reference "文件1" and "文件2" instead of "业务记录数" or "财务记录数"

#### Scenario: Rule configuration
- **WHEN** user configures field mappings
- **THEN** system displays field sources as "文件1(字段X)" and "文件2(字段Y)" instead of "业务" and "财务"

### Requirement: Internal file type identification
The system SHALL maintain internal business/finance file type identification for reconciliation logic purposes.

#### Scenario: File type detection
- **WHEN** user uploads two files
- **THEN** system internally identifies each file as business or finance for matching logic

#### Scenario: Field mapping by source
- **WHEN** user configures field mapping rules
- **THEN** system maps fields to correct file sources internally (business/finance) regardless of displayed terminology
