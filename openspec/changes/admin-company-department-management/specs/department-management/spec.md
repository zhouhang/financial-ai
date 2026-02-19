## ADDED Requirements

### Requirement: Admin can create department
The system SHALL allow administrators to create new departments. The department MUST be associated with a company.

#### Scenario: Admin creates department successfully
- **WHEN** admin provides company_id and department name, calls create_department
- **THEN** system creates the department and returns success

#### Scenario: Department name already exists in company
- **WHEN** admin tries to create a department with duplicate name in the same company
- **THEN** system returns error: "该公司下已存在此部门名称"


### Requirement: Admin can list departments by company
The system SHALL allow administrators to view all departments for a specific company.

#### Scenario: Admin lists departments
- **WHEN** admin calls list_departments with company_id
- **THEN** system returns list of departments in that company
