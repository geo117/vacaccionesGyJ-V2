import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Se ignoran con `**/` para que el patrón funcione sin importar desde qué
  // directorio se invoque ESLint. `dist/` es la salida de Vite; `node_modules`
  // y los directorios de verificación local (`.verify`, `.medir`) son
  // artefactos temporales, no código del proyecto.
  globalIgnores(['**/dist/**', '**/node_modules/**', '**/.verify/**', '**/.medir/**']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // Configuración de Vite y ESLint: se ejecutan en Node, no en el navegador.
    files: ['vite.config.js', 'eslint.config.js'],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    // Pruebas: se ejecutan con `node --test`, en Node.
    files: ['tests/**/*.mjs'],
    languageOptions: {
      globals: globals.node,
    },
  },
])
