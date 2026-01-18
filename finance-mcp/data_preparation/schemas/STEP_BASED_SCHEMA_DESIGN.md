# Step-Based Schema Design for Data Preparation

## Overview

This document describes the new step-based schema structure that supports sequential data preparation workflows where later steps can read from and depend on earlier steps' results.

## Key Requirements

1. **Sequential Execution**: Steps execute in order, not in parallel
2. **Template as Data Source**: Steps can read data from the template (previously written data)
3. **Cross-Step Dependencies**: Later steps can use data from earlier steps as matching conditions
4. **Flexible Workflow**: Support complex workflows like:
   - Step 1: Read excelA → write to template
   - Step 2: Read template data → use as condition to match excelB → write to template
   - Step 3: Read template data → use as condition to match excelC → write to template

## New Schema Structure

### 1. Top-Level Structure

```json
{
  "version": "3.0",
  "schema_type": "step_based",
  "metadata": {
    "project_name": "项目名称",
    "author": "作者",
    "created_at": "2026-01-16",
    "description": "描述"
  },
  "template_config": {
    "template_file": "模板文件.xlsx",
    "output_filename_pattern": "输出_{timestamp}.xlsx"
  },
  "processing_steps": [
    // Array of step definitions
  ],
  "workflow_controls": {
    // Workflow configuration
  }
}
```

### 2. Processing Steps Structure

Each step in `processing_steps` array has the following structure:

```json
{
  "step_id": "step_1",
  "step_name": "读取excelA并写入模板",
  "step_type": "extract_and_write",
  "depends_on": [],
  "enabled": true,

  "data_source": {
    "source_type": "uploaded_file",
    "file_pattern": "excelA_*.xlsx",
    "extraction_rules": {
      // Standard extraction rules
    }
  },

  "template_action": {
    "action_type": "write_table",
    "target": {
      "sheet": "Sheet1",
      "range": "A1:E100",
      "header_mapping": {}
    }
  },

  "output_variables": {
    "step_1_data": {
      "description": "excelA写入模板的数据",
      "fields": ["field1", "field2"]
    }
  }
}
```

### 3. Step Types

#### 3.1 extract_and_write
Extract data from source and write to template.

#### 3.2 read_template_and_match
Read data from template, use it to match another source, then write results.

#### 3.3 transform_and_write
Perform calculations/transformations and write results.

#### 3.4 conditional_write
Write data based on conditions.

### 4. Data Source Types

#### 4.1 uploaded_file
Read from uploaded Excel/CSV files.

```json
"data_source": {
  "source_type": "uploaded_file",
  "file_pattern": "bank_*.xlsx",
  "extraction_rules": {
    "sheet_name": "Sheet1",
    "range": "A2:Z1000",
    "columns_mapping": {},
    "conditional_extractions": {}
  }
}
```

#### 4.2 template_range
Read from template (previously written data).

```json
"data_source": {
  "source_type": "template_range",
  "template_reference": {
    "sheet": "Sheet1",
    "range": "A1:E100",
    "columns_mapping": {
      "A": "field1",
      "B": "field2"
    }
  }
}
```

#### 4.3 step_output
Reference output from a previous step.

```json
"data_source": {
  "source_type": "step_output",
  "step_id": "step_1",
  "variable_name": "step_1_data"
}
```

### 5. Cross-Step Matching

Steps can use data from previous steps as matching conditions:

```json
{
  "step_id": "step_2",
  "step_name": "根据step1数据匹配excelB",
  "depends_on": ["step_1"],

  "data_source": {
    "source_type": "uploaded_file",
    "file_pattern": "excelB_*.xlsx",
    "extraction_rules": {
      "conditional_extractions": {
        "condition": {
          "type": "match_with_step",
          "reference_step": "step_1",
          "reference_fields": ["field1", "field2"],
          "match_fields": ["columnA", "columnB"],
          "match_type": "inner_join"
        }
      }
    }
  }
}
```

### 6. Template Actions

#### 6.1 write_value
Write a single value to a cell.

```json
"template_action": {
  "action_type": "write_value",
  "target": {
    "sheet": "Sheet1",
    "cell": "A1",
    "value_source": "calculation_result"
  }
}
```

#### 6.2 write_table
Write a table/DataFrame to a range.

```json
"template_action": {
  "action_type": "write_table",
  "target": {
    "sheet": "Sheet1",
    "range": "A1:E100",
    "header_mapping": {
      "field1": "A",
      "field2": "B"
    },
    "write_mode": "append"
  }
}
```

#### 6.3 write_matched
Write matched data based on key fields.

```json
"template_action": {
  "action_type": "write_matched",
  "target": {
    "sheet": "Sheet1",
    "match_by": {
      "template_fields": ["A", "B"],
      "data_fields": ["key1", "key2"]
    },
    "write_columns": {
      "field3": "C",
      "field4": "D"
    }
  }
}
```

## Example: Complete Step-Based Workflow

See `step_based_example_schema.json` for a complete example implementing the workflow:
1. Read excelA → write to template
2. Read template → match excelB → write to template
3. Read template → match excelC → write to template
4. Read template → match excelD → write to template

## Implementation Changes Required

### 1. New Components

- **TemplateReader**: Read data from template Excel file
- **StepExecutor**: Execute individual steps in sequence
- **StepDependencyResolver**: Resolve step dependencies and execution order

### 2. Modified Components

- **ProcessingEngine**: Support step-based execution instead of parallel extraction
- **DataExtractor**: Support template as data source
- **Conditional Extraction**: Support cross-step matching conditions

### 3. Data Flow

```
1. Load schema and validate
2. Resolve step dependencies and execution order
3. For each step in order:
   a. Check dependencies are satisfied
   b. Read data from source (file or template)
   c. Apply conditional extractions (may reference previous steps)
   d. Perform transformations if needed
   e. Write to template
   f. Store output variables for later steps
4. Generate final output and report
```

## Backward Compatibility

- Old schemas (version 2.0) will continue to work
- Schema version field determines which processing mode to use
- `schema_type: "step_based"` explicitly enables new mode

## Migration Path

Existing schemas can be converted to step-based format by:
1. Converting each data_source to a separate step
2. Converting template_mapping to template_action in each step
3. Adding step dependencies based on execution_order
