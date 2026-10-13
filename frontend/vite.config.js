import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Configuración del servidor de desarrollo.
//
// El proxy /api evita CORS por completo en desarrollo: el navegador sólo habla
// con http://127.0.0.1:5173 y Vite reenvía al backend. Las peticiones del
// frontend nunca llevan la cadena de conexión ni credenciales de SQL Server.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_BASE_URL || 'http://127.0.0.1:5000'

  return {
    plugins: [react()],
    server: {
      host: env.VITE_DEV_HOST || '127.0.0.1',
      port: Number(env.VITE_DEV_PORT) || 5173,
      strictPort: true,
      proxy: env.VITE_API_BASE_URL
        ? undefined
        : {
            '/api': {
              target: apiTarget,
              changeOrigin: false,
              secure: false,
            },
          },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
