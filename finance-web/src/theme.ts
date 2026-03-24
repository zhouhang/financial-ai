export const STORAGE_KEY_THEME = 'tally_theme_mode';

export type ThemeMode = 'light' | 'dark';

function disableThemeTransitionsTemporarily(): void {
  const style = document.createElement('style');
  style.appendChild(document.createTextNode(`
    *, *::before, *::after {
      transition: none !important;
      animation-duration: 0s !important;
    }
  `));

  document.head.appendChild(style);
  void window.getComputedStyle(document.documentElement).opacity;

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      style.remove();
    });
  });
}

export function resolveInitialTheme(): ThemeMode {
  const savedTheme = localStorage.getItem(STORAGE_KEY_THEME);
  if (savedTheme === 'light' || savedTheme === 'dark') {
    return savedTheme;
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(
  theme: ThemeMode,
  options: {
    disableTransitions?: boolean;
    persist?: boolean;
  } = {},
): void {
  const { disableTransitions = false, persist = true } = options;
  const root = document.documentElement;
  const themeChanged = root.dataset.theme !== theme;

  if (themeChanged && disableTransitions) {
    disableThemeTransitionsTemporarily();
  }

  root.dataset.theme = theme;
  root.style.colorScheme = theme;

  if (persist) {
    localStorage.setItem(STORAGE_KEY_THEME, theme);
  }
}
