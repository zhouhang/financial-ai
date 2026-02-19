## ADDED Requirements

### Requirement: Admin can login with username and password
The system SHALL allow administrators to login with username and password. The system MUST verify credentials against the admins table.

#### Scenario: Successful admin login
- **WHEN** admin enters correct username and password
- **THEN** system returns success with admin_token

#### Scenario: Invalid credentials
- **WHEN** admin enters incorrect username or password
- **THEN** system returns error: "用户名或密码错误"


### Requirement: Admin logout
The system SHALL allow administrators to logout by invalidating the admin_token.

#### Scenario: Admin logout
- **WHEN** admin calls logout with valid admin_token
- **THEN** system invalidates the token
