import { STRINGS } from '@/config/strings';

interface ClearVoiceLogoProps {
  className?: string;
  variant?: 'full' | 'mark';
}

export function ClearVoiceLogo({ className = '', variant = 'full' }: ClearVoiceLogoProps) {
  return (
    <img
      src="/logo.png"
      alt={STRINGS.brand.logoAriaLabel}
      className={className}
    />
  );
}
