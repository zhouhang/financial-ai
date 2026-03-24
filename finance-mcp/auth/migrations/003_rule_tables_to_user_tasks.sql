BEGIN;

ALTER TABLE bus_rules RENAME TO rule_detail;
ALTER TABLE rule_detail ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE rule_detail RENAME COLUMN memo TO remark;

UPDATE rule_detail AS rd
SET rule = jsonb_set(
    CASE
        WHEN jsonb_typeof(rd.rule::jsonb) = 'object' THEN rd.rule::jsonb
        ELSE '{}'::jsonb
    END,
    '{file_rule_code}',
    to_jsonb(bar.file_rule_code),
    true
)::jsonb
FROM bus_agent_rules AS bar
WHERE rd.rule_code = bar.code
  AND bar.file_rule_code IS NOT NULL
  AND bar.file_rule_code <> '';

CREATE TABLE user_tasks (
    id integer PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    task_code character varying(255) NOT NULL,
    task_name character varying(255) NOT NULL,
    description text
);

INSERT INTO user_tasks (id, user_id, task_code, task_name, description)
SELECT
    bar.id,
    NULL::uuid AS user_id,
    bar.code AS task_code,
    bar.name AS task_name,
    bar.desc_text AS description
FROM bus_agent_rules AS bar
WHERE bar.parent_code IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM rule_detail AS rd
      WHERE rd.rule_code = bar.code
  );

DROP TABLE bus_agent_rules;

CREATE INDEX idx_user_tasks_task_code ON user_tasks(task_code);
CREATE INDEX idx_user_tasks_user_id ON user_tasks(user_id);
CREATE INDEX idx_rule_detail_rule_code ON rule_detail(rule_code);
CREATE INDEX idx_rule_detail_user_id ON rule_detail(user_id);

COMMIT;
