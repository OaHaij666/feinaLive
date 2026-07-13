import { computed, ref } from 'vue'

export type ConsoleTheme = 'dark' | 'light'

const STORAGE_KEY = 'feina-console-theme'

function readInitialTheme(): ConsoleTheme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' ? 'light' : 'dark'
}

const theme = ref<ConsoleTheme>(readInitialTheme())

function applyTheme(value: ConsoleTheme) {
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
  const themeMeta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (themeMeta) themeMeta.content = value === 'light' ? '#f5f3ff' : '#0b1020'
}

applyTheme(theme.value)

export function useConsoleTheme() {
  const isLight = computed(() => theme.value === 'light')

  function setTheme(value: ConsoleTheme) {
    theme.value = value
    localStorage.setItem(STORAGE_KEY, value)
    applyTheme(value)
  }

  function toggleTheme() {
    setTheme(isLight.value ? 'dark' : 'light')
  }

  return { theme, isLight, setTheme, toggleTheme }
}
