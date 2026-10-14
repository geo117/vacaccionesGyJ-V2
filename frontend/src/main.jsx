import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

/* Orden de estilos deliberado:
   1. `bootstrap`            → framework base. Se importa COMPLETO y no solo
      Reboot + utilidades: react-bootstrap usa muchas clases del framework
      (`.modal`, `.form-control`, `.popover`, `.alert`, `.btn-*`) y sin ellas los
      componentes se renderizan sin posición ni tamaño —un modal aparecía en
      `position: static`, empujado al flujo de la página—.
   2. `sweetalert2`          → estilos del diálogo de confirmación.
   3. tokens + layout + modal → el sistema de diseño del proyecto. Va DESPUÉS
      para que sus reglas ganen la cascada sobre las del framework. */
import 'bootstrap/dist/css/bootstrap.min.css'
import 'sweetalert2/dist/sweetalert2.min.css'
import './styles/tokens.css'
import './styles/layout.css'
import './styles/modal.css'

import App from './App.jsx'
import AuthProvider from './auth/AuthProvider'
import NotificacionesProvider from './notifications/NotificacionesProvider'

const container = document.getElementById('root')
if (!container) {
  throw new Error('No se encontró el contenedor #root en index.html.')
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <NotificacionesProvider>
          <App />
        </NotificacionesProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
