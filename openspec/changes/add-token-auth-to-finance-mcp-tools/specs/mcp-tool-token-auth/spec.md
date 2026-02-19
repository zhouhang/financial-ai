## ADDED Requirements

### Requirement: Token required for data_preparation_start
The system SHALL require a valid auth_token when calling the data_preparation_start tool. The token SHALL be validated using the auth.jwt_utils.get_user_from_token function.

#### Scenario: Valid token provided
- **WHEN** user calls data_preparation_start with a valid auth_token
- **THEN** the tool SHALL execute the data preparation task and return the result

#### Scenario: Missing token
- **WHEN** user calls data_preparation_start without auth_token
- **THEN** the tool SHALL return an error: "缺少 auth_token 参数"

#### Scenario: Invalid token
- **WHEN** user calls data_preparation_start with an invalid or expired auth_token
- **THEN** the tool SHALL return an error: "token 无效或已过期"

### Requirement: Token required for data_preparation_result
The system SHALL require a valid auth_token when calling the data_preparation_result tool.

#### Scenario: Valid token provided
- **WHEN** user calls data_preparation_result with a valid auth_token
- **THEN** the tool SHALL return the task result

#### Scenario: Missing token
- **WHEN** user calls data_preparation_result without auth_token
- **THEN** the tool SHALL return an error: "缺少 auth_token 参数"

### Requirement: Token required for data_preparation_status
The system SHALL require a valid auth_token when calling the data_preparation_status tool.

#### Scenario: Valid token provided
- **WHEN** user calls data_preparation_status with a valid auth_token
- **THEN** the tool SHALL return the task status

#### Scenario: Missing token
- **WHEN** user calls data_preparation_status without auth_token
- **THEN** the tool SHALL return an error: "缺少 auth_token 参数"

### Requirement: Token required for data_preparation_list_tasks
The system SHALL require a valid auth_token when calling the data_preparation_list_tasks tool.

#### Scenario: Valid token provided
- **WHEN** user calls data_preparation_list_tasks with a valid auth_token
- **THEN** the tool SHALL return the list of all tasks for the authenticated user

#### Scenario: Missing token
- **WHEN** user calls data_preparation_list_tasks without auth_token
- **THEN** the tool SHALL return an error: "缺少 auth_token 参数"
