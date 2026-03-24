UPDATE rule_detail
SET rule = $${
  "rule_id": "XM_26_RECONC_001",
  "rule_name": "喜马-26合单与官网数据核对",
  "description": "将合单文件与官网文件进行核对，通过 sup 订单号与第三方订单号关联，比对应结算金额差异",
  "file_rule_code": "audio_recon_file_check",
  "schema_version": "1.6",
  "rules": [
    {
      "enabled": true,
      "source_file": {
        "table_name": "喜马合单表",
        "description": "源文件定义（合单文件）",
        "identification": {
          "match_by": "table_name",
          "description": "通过文件校验阶段识别的表名匹配源文件",
          "match_value": "喜马合单表",
          "match_strategy": "exact"
        }
      },
      "target_file": {
        "table_name": "喜马官网表",
        "description": "目标文件定义（官网文件）",
        "identification": {
          "match_by": "table_name",
          "description": "通过文件校验阶段识别的表名匹配目标文件",
          "match_value": "喜马官网表",
          "match_strategy": "exact"
        }
      },
      "recon": {
        "description": "核对配置",
        "key_columns": {
          "match_type": "exact",
          "description": "用于关联源文件与目标文件的关键列映射（相当于 JOIN 条件），支持多字段映射",
          "mappings": [
            {
              "source_field": "sup订单号",
              "target_field": "第三方订单号"
            }
          ],
          "transformations": {
            "source": {
              "sup订单号": [
                { "type": "strip_prefix", "value": "'" },
                { "type": "regex_replace", "pattern": "^(.{1,21}).*$", "replacement": "\\1" }
              ]
            },
            "target": {
              "第三方订单号": [
                { "type": "regex_replace", "pattern": "_\\\\d+$", "replacement": "" },
                { "type": "regex_replace", "pattern": "^(.{1,21}).*$", "replacement": "\\1" }
              ]
            }
          }
        },
        "compare_columns": {
          "description": "需要比对的数值列",
          "columns": [
            {
              "name": "发生减",
              "tolerance": 0.01,
              "description": "合单发生- 与 官网应结算平台金额比对，允许 0.01 的绝对误差",
              "compare_type": "numeric",
              "source_column": "发生-",
              "target_column": "应结算平台金额"
            }
          ]
        },
        "aggregation": {
          "enabled": true,
          "group_by": [
            {
              "source_field": "sup订单号",
              "target_field": "第三方订单号"
            }
          ],
          "description": "分组聚合配置，启用后先按 source/target 对应字段分组聚合，再进行比对",
          "aggregations": [
            {
              "alias": "应结算平台金额汇总",
              "source_field": "发生-",
              "target_field": "应结算平台金额",
              "function": "sum"
            }
          ]
        }
      },
      "output": {
        "format": "xlsx",
        "sheets": {
          "summary": {
            "name": "核对汇总",
            "enabled": true,
            "description": "输出核对结果汇总信息，包括总记录数、匹配数、差异数等"
          },
          "source_only": {
            "name": "合单独有",
            "enabled": true,
            "description": "仅在合单文件中存在的记录"
          },
          "target_only": {
            "name": "官网独有",
            "enabled": true,
            "description": "仅在官网文件中存在的记录"
          },
          "matched_with_diff": {
            "name": "差异记录",
            "enabled": true,
            "description": "关键列匹配但数值有差异的记录详情"
          }
        },
        "file_name_template": "喜马26_{rule_name}_核对结果_{timestamp}"
      }
    }
  ]
}$$::jsonb
WHERE id = 4;
