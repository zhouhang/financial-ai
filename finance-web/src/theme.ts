export const STORAGE_KEY_THEME = 'tally_theme_mode';

export type ThemeMode = 'light' | 'dark';

type ThemeListener = () => void;

const themeListeners = new Set<ThemeListener>();
let currentTheme: ThemeMode | null = null;

function emitThemeChange(): void {
  themeListeners.forEach((listener) => listener());
}

function readThemeFromDom(): ThemeMode | null {
  if (typeof document === 'undefined') {
    return null;
  }

  const theme = document.documentElement.dataset.theme;
  return theme === 'light' || theme === 'dark' ? theme : null;
}

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

export function getThemeMode(): ThemeMode {
  const domTheme = readThemeFromDom();
  if (domTheme) {
    currentTheme = domTheme;
    return domTheme;
  }

  if (currentTheme) {
    return currentTheme;
  }

  if (typeof window !== 'undefined') {
    currentTheme = resolveInitialTheme();
    return currentTheme;
  }

  return 'light';
}

export function subscribeTheme(listener: ThemeListener): () => void {
  themeListeners.add(listener);
  return () => {
    themeListeners.delete(listener);
  };
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
  currentTheme = theme;
  if (!root.classList.contains('theme-ready')) {
    requestAnimationFrame(() => {
      root.classList.add('theme-ready');
    });
  }

  if (persist) {
    localStorage.setItem(STORAGE_KEY_THEME, theme);
  }

  if (themeChanged) {
    emitThemeChange();
  }
}

export function toggleTheme(): ThemeMode {
  const nextTheme = getThemeMode() === 'light' ? 'dark' : 'light';
  applyTheme(nextTheme);
  return nextTheme;
}
