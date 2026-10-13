/**
 * Rutas de la aplicación.
 *
 * `/login`  → acceso (público)
 * `/app`    → shell autenticado: barra superior + sidebar
 *   ├── resumen           cualquier sesión
 *   ├── asignaciones      cualquier sesión
 *   ├── notificaciones    cualquier sesión
 *   └── administracion    solo Talento Humano (RequireTalentoHumano + 403 en la API)
 *
 * Cualquier otra dirección cae en una vista de "no encontrada".
 */

import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layout/AppShell'
import RequireAuth from './auth/RequireAuth'
import RequireTalentoHumano from './auth/RequireTalentoHumano'
import AdministracionPage from './pages/AdministracionPage'
import AsignacionesPage from './pages/AsignacionesPage'
import LoginPage from './pages/LoginPage'
import NotificacionesPage from './pages/NotificacionesPage'
import NotFoundPage from './pages/NotFoundPage'
import ResumenPage from './pages/ResumenPage'
import { DEFAULT_ROUTE } from './services/navigation'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={DEFAULT_ROUTE} replace />} />
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/app" element={<AppShell />}>
          <Route index element={<Navigate to="resumen" replace />} />
          <Route path="resumen" element={<ResumenPage />} />
          <Route path="asignaciones" element={<AsignacionesPage />} />
          <Route path="notificaciones" element={<NotificacionesPage />} />

          {/* Doble puerta: la ruta exige el cargo y el backend lo vuelve a
              comprobar en cada endpoint de administración. */}
          <Route element={<RequireTalentoHumano />}>
            <Route path="administracion" element={<AdministracionPage />} />
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
