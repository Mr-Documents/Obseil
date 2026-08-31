import { createContext, useContext } from 'react';

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'obseil.theme';

export interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used inside a <ThemeProvider>.');
  }
  return context;
}
