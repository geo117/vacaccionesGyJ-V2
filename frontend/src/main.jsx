import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

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
