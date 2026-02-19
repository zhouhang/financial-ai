## ADDED Requirements

### Requirement: reconciliation_status requires authentication
The system SHALL require a valid auth_token to query reconciliation task status. The token MUST be validated using the JWT validation mechanism before returning any task information.

#### Scenario: Valid token provided
- **WHEN** user calls reconciliation_status with a valid auth_token
- **THEN** system returns the task status information

#### Scenario: Missing token
- **WHEN** user calls reconciliation_status without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"

#### Scenario: Invalid token
- **WHEN** user calls reconciliation_status with an invalid or expired auth_token
- **THEN** system returns an error: "token 无效或已过期"


### Requirement: reconciliation_result requires authentication
The system SHALL require a valid auth_token to retrieve reconciliation results. Users MUST only access results for tasks they created.

#### Scenario: Valid token and authorized task
- **WHEN** user calls reconciliation_result with a valid auth_token for a task they created
- **THEN** system returns the reconciliation result data

#### Scenario: Valid token but unauthorized task
- **WHEN** user calls reconciliation_result with a valid auth_token for a task created by another user
- **THEN** system returns an error: "无权访问该任务"

#### Scenario: Missing token
- **WHEN** user calls reconciliation_result without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"


### Requirement: reconciliation_list_tasks requires authentication
The system SHALL require a valid auth_token to list reconciliation tasks. Users MUST only see tasks they created.

#### Scenario: Valid token provided
- **WHEN** user calls reconciliation_list_tasks with a valid auth_token
- **THEN** system returns only the tasks created by the authenticated user

#### Scenario: Missing token
- **WHEN** user calls reconciliation_list_tasks without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"


### Requirement: file_upload requires authentication
The system SHALL require a valid auth_token to upload files. Files MUST be associated with the authenticated user.

#### Scenario: Valid token provided
- **WHEN** user calls file_upload with a valid auth_token and file content
- **THEN** system uploads the file and returns the file path

#### Scenario: Missing token
- **WHEN** user calls file_upload without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"


### Requirement: get_reconciliation requires authentication
The system SHALL require a valid auth_token to retrieve reconciliation configurations.

#### Scenario: Valid token provided
- **WHEN** user calls get_reconciliation with a valid auth_token
- **THEN** system returns the reconciliation configuration

#### Scenario: Missing token
- **WHEN** user calls get_reconciliation without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"


### Requirement: analyze_files requires authentication
The system SHALL require a valid auth_token to analyze uploaded files.

#### Scenario: Valid token provided
- **WHEN** user calls analyze_files with a valid auth_token and file paths
- **THEN** system analyzes the files and returns column information, row counts, and sample data

#### Scenario: Missing token
- **WHEN** user calls analyze_files without auth_token
- **THEN** system returns an error: "缺少 auth_token 参数"
