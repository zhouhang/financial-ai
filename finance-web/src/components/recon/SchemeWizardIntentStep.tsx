interface SchemeWizardIntentStepProps {
  name: string;
  onNameChange: (value: string) => void;
}

export default function SchemeWizardIntentStep({
  name,
  onNameChange,
}: SchemeWizardIntentStepProps) {
  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-5">
        <p className="text-sm font-semibold text-text-primary">先补充方案名称，再进入数据整理</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          填写方案名称后，系统再带你配置左右数据与后续试跑。
        </p>
      </div>

      <label className="block">
        <span className="text-xs font-medium text-text-secondary">方案名称</span>
        <input
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          placeholder="例如：平台结算日清方案"
        />
      </label>
    </div>
  );
}
