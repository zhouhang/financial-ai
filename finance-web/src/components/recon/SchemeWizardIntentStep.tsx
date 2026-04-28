interface SchemeWizardIntentStepProps {
  name: string;
  businessGoal: string;
  onNameChange: (value: string) => void;
  onBusinessGoalChange: (value: string) => void;
}

export default function SchemeWizardIntentStep({
  name,
  businessGoal,
  onNameChange,
  onBusinessGoalChange,
}: SchemeWizardIntentStepProps) {
  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface-secondary p-5">
        <p className="text-sm font-semibold text-text-primary">先补充方案目标，再进入数据整理</p>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          填写方案名称和对账目的后，系统再带你配置左右数据与后续试跑。
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

      <label className="block">
        <span className="text-xs font-medium text-text-secondary">对账目的</span>
        <textarea
          value={businessGoal}
          onChange={(event) => onBusinessGoalChange(event.target.value)}
          rows={6}
          className="mt-1.5 w-full rounded-2xl border border-border bg-surface px-4 py-3 text-sm leading-7 text-text-primary outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
          placeholder="例如：核对平台订单与到账账单是否一致，并提前识别漏单、少收和金额差异。"
        />
      </label>
    </div>
  );
}
