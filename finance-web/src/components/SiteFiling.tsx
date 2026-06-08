interface SiteFilingProps {
  className?: string;
}

const ICP_FILING_NUMBER = '鄂ICP备2026028755号-1';
const MIIT_FILING_URL = 'https://beian.miit.gov.cn/';

export default function SiteFiling({ className = '' }: SiteFilingProps) {
  return (
    <div className={`site-filing ${className}`.trim()} aria-label="ICP备案号">
      <a href={MIIT_FILING_URL} target="_blank" rel="noreferrer">
        {ICP_FILING_NUMBER}
      </a>
    </div>
  );
}
