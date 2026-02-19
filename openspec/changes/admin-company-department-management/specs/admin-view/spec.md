## ADDED Requirements

### Requirement: Admin can view company-department-employee-rule hierarchy
The system SHALL allow administrators to view the complete hierarchy of companies, departments, employees, and rules.

#### Scenario: Admin views hierarchy
- **WHEN** admin calls get_admin_view with valid admin_token
- **THEN** system returns hierarchical data structure with companies, departments, employees, and rules


### Requirement: User registration uses dropdown for company and department
The system SHALL allow users to select company and department from dropdown menus during registration.

#### Scenario: User registers with company and department dropdown
- **WHEN** user registers and selects company from dropdown
- **THEN** system shows department dropdown filtered by selected company

#### Scenario: No companies exist
- **WHEN** user tries to register but no companies exist
- **THEN** system shows message "暂无公司，请联系管理员创建"
