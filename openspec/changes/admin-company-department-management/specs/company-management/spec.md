## ADDED Requirements

### Requirement: Admin can create company
The system SHALL allow administrators to create new companies. The company MUST be stored in the company table.

#### Scenario: Admin creates company successfully
- **WHEN** admin provides company name and calls create_company
- **THEN** system creates the company and returns success

#### Scenario: Company name already exists
- **WHEN** admin tries to create a company with duplicate name
- **THEN** system returns error: "公司名称已存在"


### Requirement: Admin can list all companies
The system SHALL allow administrators to view all companies in the system.

#### Scenario: Admin lists companies
- **WHEN** admin calls list_companies with valid admin_token
- **THEN** system returns list of all companies
