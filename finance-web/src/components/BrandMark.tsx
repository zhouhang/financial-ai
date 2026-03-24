import { useId } from 'react';

interface BrandMarkProps {
  className?: string;
}

export default function BrandMark({ className = 'h-10 w-10' }: BrandMarkProps) {
  const gradientId = useId();
  const glowId = useId();

  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <linearGradient id={gradientId} x1="9" y1="6" x2="38" y2="42" gradientUnits="userSpaceOnUse">
          <stop stopColor="#60A5FA" />
          <stop offset="0.55" stopColor="#2563EB" />
          <stop offset="1" stopColor="#1D4ED8" />
        </linearGradient>
        <linearGradient id={glowId} x1="12" y1="10" x2="31" y2="31" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFFFFF" stopOpacity="0.45" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect x="4" y="4" width="40" height="40" rx="14" fill={`url(#${gradientId})`} />
      <path
        d="M12 11C12 9.89543 12.8954 9 14 9H26C18.8203 11.2922 14.2922 15.8203 12 23V11Z"
        fill={`url(#${glowId})`}
      />
      <rect x="13" y="14" width="2.75" height="18" rx="1.375" fill="white" fillOpacity="0.95" />
      <rect x="20" y="19" width="2.75" height="13" rx="1.375" fill="white" fillOpacity="0.88" />
      <rect x="27" y="23" width="2.75" height="9" rx="1.375" fill="white" fillOpacity="0.82" />
      <path
        d="M14.5 29L21.2 22.2L26.4 25.7L34 17.5"
        stroke="white"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="34" cy="17.5" r="2.25" fill="#F8FAFC" />
      <circle cx="34" cy="17.5" r="1.1" fill="#2563EB" />
    </svg>
  );
}
