# Frontend — Gestión de Vacaciones G&J

Interfaz en React + Vite: **acceso autenticado contra SQL Server** y el shell
interno (barra superior + sidebar de tres opciones).

## Puesta en marcha

El backend debe estar corriendo antes (`../backend`, `python app.py`).

```powershell
npm install
npm run dev
```

Abre `http://127.0.0.1:5173`.

| Script | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con HMR |
| `npm run build` | Build de producción en `dist/` |
| `npm run lint` | ESLint |
| `npm test` | Pruebas de la lógica de períodos, del reporte y de las descargas |
| `npm run preview` | Sirve el build de producción |

### Sobre los estilos de Bootstrap

Se importa `bootstrap.min.css` **completo**, no sólo Reboot y utilidades:
react-bootstrap usa muchas clases del framework (`.modal`, `.form-control`,
`.popover`, `.alert`, `.btn-*`) y sin ellas los componentes se renderizan sin
posición ni tamaño. Los estilos del proyecto (`styles/`) se cargan **después**,
así que sus reglas ganan la cascada.

## Vista de asignaciones

Es la vista con más operaciones. La columna **Acciones** de cada fila es un menú
de tres puntos (react-bootstrap `Dropdown`) con las tres operaciones, más una
cuarta que sólo aparece en las filas rechazadas.

| Acción | Qué hace |
|---|---|
| **Descargar** (cabecera) | Submenú con dos documentos que genera el servidor con las plantillas oficiales: la **planilla** de vacaciones en PDF y el **plano UNOEE** en Excel. El plano sólo lo ve Talento Humano. |
| **Ver empleado** | Ficha de consulta: datos del colaborador, los tres períodos con sus días calculados, total, observaciones y motivo de rechazo si lo hay. Desde aquí se puede vaciar los períodos. |
| **Asignar fechas** | Modal con los tres períodos **en una fila de columnas**, el total como cuarta columna, fecha de ingreso sugerida y observaciones. |
| **Aprobar / rechazar** | Modal de decisión. Al rechazar, el motivo es **obligatorio** y hay un recuadro para escribirlo. |
| **Ver motivo del rechazo** | Sólo en filas rechazadas: muestra el motivo en una alerta. |

### El menú de acciones

El disparador es un botón cuadrado con tres puntos y `aria-label` que nombra al
colaborador y el radicado («Acciones para Ana María Restrepo, radicado
ACT-3041»): en una tabla con once filas, once botones idénticos sin nombre
accesible serían inservibles con lector de pantalla.

Tres decisiones que conviene no perder al tocar el componente:

* **Es un `Popover`, no un `Dropdown`.** El `Dropdown` de react-bootstrap aplica
  sus propios modificadores de Popper (`flip` a `left-end`/`left-start` y el
  `margin-top` de Bootstrap) que competían entre sí: el menú quedaba descentrado
  y, en algunas filas, del lado contrario. El `Popover` usa `preventOverflow` y
  `strategy: fixed` por defecto, que es justo lo que hace falta porque el
  contenedor de la tabla tiene `overflow-x: auto` y recortaría un menú
  posicionado en absoluto.
* **`placement="left-start"`**: abre siempre a la **izquierda** del botón y a su
  misma altura, en el primer clic y en los siguientes. Verificado con
  desplazamiento vertical 0 respecto al botón.
* **El estado abierto vive en la página** (`menuAbierto`), no dentro del popover.
  Eso permite cerrar el menú al elegir una opción y garantiza que sólo haya uno
  abierto a la vez. `rootClose` añade el cierre con clic fuera y con Escape.

Cada ítem lleva icono **y** texto, nunca sólo el icono.

### Cálculo de los días

Los días **nunca** se escriben a mano: se derivan de las fechas.

* Un rango cuenta ambos extremos: del 1 al 5 de marzo son **5** días.
* El cálculo se hace en UTC, para que el cambio de horario de verano no añada ni
  quite un día.
* Un período a medias se muestra como "Incompleto", no como 0: "no programado" y
  "cero días" son cosas distintas y confundirlas daría un total creíble pero
  falso.
* Se valida que la fecha de fin no sea anterior al inicio y que **los períodos
  no se crucen** —el error que de verdad descuadra la nómina—, y cada período
  nombra con cuál choca.
* La fecha de ingreso se propone como el día siguiente al último período, con un
  botón para aplicarla; se propone, no se impone.

La lógica vive en `src/utils/periodos.js` (pura y sin React) y el estado en
`src/hooks/useAsignaciones.js`, de modo que la tabla y los modales leen los
mismos datos y no pueden divergir.

### Las descargas

El botón **Descargar** de la cabecera abre un submenú con dos documentos que arma
el **servidor** con las plantillas institucionales, no el navegador. Cada opción
abre su propio modal:

* **Planilla** de vacaciones en **PDF** (`/api/reportes/planilla`). Talento Humano
  elige la UNES en un desplegable (`DescargarPlanillaModal`); los demás cargos
  descargan la suya **sin modal**, porque el servidor limita el PDF a la UNES de
  la sesión.
* **Plano UNOEE** en **Excel** (`/api/reportes/plano-unoee`), sobre
  `backend/planos_unoee/ARCHIVO PLANO TNL-VACACIONES.xlsx`.
  `DescargarPlanoModal` ofrece **plano general** (toda la plantilla) o **plano por
  UNES** (con el desplegable). **Exclusivo de Talento Humano**: además de
  ocultarse la opción, el backend responde `403` si otro cargo llama a la API.

El desplegable de UNES se arma con las UNES de la tabla, ya cargadas
(`opcionesUnes`), así que no hay una petición extra. La búsqueda y el filtro de
estado del navegador **no viajan**: los documentos son por UNES, que es como
están definidos.

El nombre del archivo lo propone el servidor en `Content-Disposition` y
`src/utils/descargas.js` lo lee (`filename*` con UTF-8 primero, para no perder
tildes); si no llegara, se usa un nombre de reserva.

El generador de CSV de `src/utils/reporte.js` se conserva —y sigue cubierto por
pruebas— como volcado crudo reutilizable, pero la cabecera ya no lo ofrece.

## Cómo llega el frontend a la API

Por defecto `VITE_API_BASE_URL` está **vacío** y el proxy de `vite.config.js`
reenvía `/api` a `http://127.0.0.1:5000`. Así el navegador solo habla con su
propio origen y CORS ni se activa en desarrollo.

Si defines `VITE_API_BASE_URL` (copia `.env.example` a `.env`), el navegador
llamará directo a esa URL y el origen del frontend debe estar en
`CORS_ORIGINS2` del backend.

## Rutas

| Ruta | Acceso | Contenido |
|---|---|---|
| `/` | — | Redirige a `/app/resumen` |
| `/login` | Público | Correo y contraseña; **UNES** sólo si el cargo la necesita |
| `/app/resumen` | Sesión | Indicadores y consolidado de **todos** los empleados |
| `/app/asignaciones` | Sesión | Plantilla de la UNES —**toda la empresa** para Talento Humano— con búsqueda, filtros, paginación y las tres operaciones |
| `/app/notificaciones` | Sesión | Bandeja del cargo y los avisos que uno mismo generó |
| `/app/administracion` | **Talento Humano** | Usuarios: crear, editar, activar/desactivar y eliminar |
| `*` | — | Vista de "no encontrada" |

## El campo UNES del login

Va **a la izquierda de la contraseña**: son tres dígitos y no necesita el ancho
completo. El campo filtra a dígitos mientras se escribe y exige tres **si se
escribe algo**.

Es **opcional**: Talento Humano entra sólo con correo y contraseña, porque su
tablero es la plantilla completa y no hay unidad que elegir. Para los demás
cargos el servidor responde `400 UNES_REQUERIDA` tras comprobar las credenciales
—nunca antes, para no delatar qué correos existen— y el formulario señala el
campo sin borrar lo ya escrito.

La UNES **no se guarda en la base**: viaja en el login, el servidor la mete en la
sesión y la usa para filtrar. Se acepta `109` y `2-109`.

## El sidebar

Se muestra y se oculta con la **hamburguesa de la esquina superior izquierda**, a
cualquier ancho de pantalla. En móvil entra como panel deslizante que se cierra con
Escape o tocando fuera, y el foco vuelve al botón que lo abrió; en pantalla ancha,
ocultarlo devuelve el ancho al contenido. Todo el comportamiento está en CSS: el
contenedor lleva `data-nav="abierto" | "oculto"` y los media queries deciden qué
significa en cada tamaño. No hay estilos en línea que peleen con ellos.

## La tabla de asignaciones

Una fila por **colaborador**, no por asignación: los que todavía no tienen fechas
programadas aparecen igual (atenuados), porque son justamente a quienes hay que
programárselas. Sobre ellos, «Asignar fechas» abre el modal de creación **con sus
datos ya precargados** desde la vista de la empresa.

La tabla muestra la plantilla de la UNES de la sesión; Talento Humano, que entra
sin UNES, recibe **toda la plantilla** y por eso tiene disponible el filtro de
UNES en la barra.

Se pagina **de a 20 registros** con el `Pagination` de react-bootstrap, debajo de
la tabla: primera, anterior, números, siguiente y última. La búsqueda y los
filtros se aplican **antes** de paginar, así que el total que se anuncia es el de
los filtros y cambiar cualquiera de ellos vuelve a la primera página.

| Columna | De dónde sale |
|---|---|
| Desc. Unes | `DescCO` |
| Colaborador | `Empleado` |
| Identificación | `cedula` |
| UNES | `IDCia_CO` |
| Cargo | `Cargo` |
| Estado | `pendiente` hasta que se apruebe o rechace |
| Corte | `dias_vacaciones_corteDic` |
| Asignados | el total de los períodos programados |
| A usar | **corte − asignados**, con semáforo |

Los encabezados numéricos van cortos («Corte», «Asignados», «A usar») porque el
nombre completo no cabía en su columna; el nombre entero está en el `title` y en
el texto para lectores de pantalla.

**Semáforo de «A usar»**: menos de −3 en rojo (programó más días de los que
tiene), de −3 a 10 en amarillo, más de 10 en verde (le quedan días). Siempre con
un decimal. El color nunca es la única señal: la celda lleva la etiqueta para
lectores de pantalla y un `title` con la operación completa.

De ese mismo umbral sale «**Aplica licencia**» en la ficha del colaborador: por
debajo del rojo el exceso se paga como **licencia no remunerada**; en cualquier
otro caso, «No aplica» en verde. La regla se consulta a `semaforoDiasAUsar` en
lugar de repetir el −3, de modo que el color de la tabla y este veredicto no
puedan contradecirse. En la misma ficha, «Aprobado por» / «Rechazado por» sale
del estado de la asignación —y del nombre que la base ya guarda— y una
asignación pendiente dice «Pendiente de aprobación» en lugar de atribuirle la
decisión a alguien.

El mismo cálculo aparece en los dos modales con los mismos tonos, así que el
número se mueve mientras se escriben los períodos:

* **Nueva asignación**: «Días a usar» dentro del resumen, justo debajo de «Total
  asignado», con la operación a la vista (`7,2 a corte − 20,0 asignados`). Los
  días a corte **no se editan** en este modal: vienen de la vista del colaborador,
  y si la fila no los trajera se dice «sin dato» en lugar de calcular sobre cero.
* **Editar fechas**: la misma línea dentro del resumen, debajo del total.

Si el servidor corporativo no responde, el servidor degrada al listado local y la
pantalla lo advierte con un aviso; no se queda en blanco.

Las opciones del menú salen de una única definición en
`src/services/navigation.js`. La marca `soloTalentoHumano` hace que el sidebar
**no dibuje** «Administración» para otros cargos, y la ruta está detrás de
`RequireTalentoHumano`. Ninguno de los dos es el control real: el backend
responde 403 en los endpoints de administración.

## El cargo manda

`GET /api/auth/session` y el login devuelven `cargo`, `esTalentoHumano` y
`puedeAprobar`. La interfaz los usa **sólo para mostrar u ocultar opciones**:

| | Talento Humano | Otro cargo |
|---|---|---|
| Opción «Administración» en el sidebar | sí | oculta |
| Ruta `/app/administracion` | carga | muestra «Esta sección es de Talento Humano» |
| Opción «Aprobar / rechazar» en el menú de asignaciones | sí | oculta |
| Opción «Descargar plano UNOEE» | sí | oculta |
| Tablero de asignaciones | toda la plantilla | sólo su UNES |
| Bandeja general de notificaciones | todo | vacía |
| Avisos que uno mismo generó (`usuario_id`) | sí | sí |
| Aviso «tu cargo sólo consulta» | no | sí |
| Opción «Desactivar» sobre su propia cuenta | no (deshabilitada) | — |

Ocultar una opción es comodidad, no seguridad: el backend responde `403` si
cualquier otro cargo llama a la API directamente. Está comprobado en las pruebas.

## Administración de usuarios

La tabla de usuarios usa el mismo menú de tres puntos que la de asignaciones:
**Editar**, **Activar / Desactivar** y **Eliminar**. La columna **Estado** muestra
`Activo` o `Inactivo`, y las filas inactivas se atenúan.

Dos opciones quedan deshabilitadas con el motivo en el `title`, y el backend
también las rechaza:

* **Desactivar o eliminar tu propio usuario.** Sería cerrarte la sesión a ti mismo
  sin querer.
* **Desactivar al último Talento Humano activo.** Dejaría el sistema sin nadie que
  administre.

## Notificaciones

Los avisos **los redacta y guarda el servidor** al programar fechas, aprobar o
rechazar, y en `usuario_id` queda el id de **quien hizo la acción**.

El contador que aparece en la opción «Notificaciones» del sidebar es el número de
avisos que la persona **todavía no ha revisado**, y se apaga al abrir la bandeja.
Lo lleva `src/notifications/`: la lista de avisos es el mismo dato para el contador
y para la pantalla —si cada uno pidiera su copia, el número y el contenido podrían
discrepar— y los ids ya vistos se guardan en `localStorage`, con una clave por
usuario.

`dbo.notificaciones` **no tiene columna de «leída»**, y por eso el estado de
revisión vive en el navegador: no se simula una verdad del servidor. La
consecuencia, dicha en voz alta, es que en otro equipo los avisos vuelven a contar
como pendientes. Lo que sí es del servidor es el filtrado por cargo, en el `WHERE`
de la consulta. Dentro de la bandeja sólo se pueden filtrar por tipo (asignación,
aprobación, rechazo), que se deduce del texto que redactó el servidor.

## Cómo funciona la autenticación

1. `POST /api/auth/login` con correo y contraseña —y la UNES si el cargo la pide—.
2. El backend responde un token opaco; se guarda en **`sessionStorage`** (muere
   al cerrar la pestaña, a diferencia de `localStorage`).
3. Viaja en el encabezado `Authorization: Bearer <token>`, nunca en una cookie:
   sin cookies no hay CSRF posible.
4. Al cargar la aplicación, `RequireAuth` **no renderiza nada protegido** hasta
   que el servidor confirma la sesión con `GET /api/auth/session`. Poseer un
   token no autentica a nadie.
5. Un `401` en cualquier llamada limpia la sesión y devuelve al acceso con un
   aviso único.
6. Salir revoca el token en el servidor y limpia el estado local aunque esa
   llamada falle.

## Datos

Ya **no hay fixtures**: la vista de asignaciones, el resumen y las notificaciones
leen de `dbo.asignacion_vacaciones`, `dbo.Usuarios` y `dbo.notificaciones` a
través de la API.

`src/mock/` sigue existiendo sólo por `operationCenters`, que se usa para poner
nombre legible a una UNES en el filtro; no representa datos de personas.

Los días y los totales los **calcula el servidor**. Al guardar, la fila se
reemplaza con la que devuelve la API en lugar de recalcularse en el navegador: si
ambos cálculos discrepacaran, gana el de la base.

## Estructura

```
src/
├── auth/
│   ├── AuthProvider.jsx          Estado de sesión y cargo
│   ├── RequireAuth.jsx           Guarda de rutas protegidas
│   ├── RequireTalentoHumano.jsx  Guarda de la ruta de administración
│   ├── context.js                El contexto (módulo aparte, por Fast Refresh)
│   └── useAuth.js                Hook de acceso con error explícito
├── components/
│   ├── Icon.jsx                  Icono por nombre (react-icons)
│   ├── Field.jsx                 Campo con etiqueta, ayuda y error
│   ├── StatusChip.jsx            Estado: color + glifo + palabra
│   ├── EmptyState.jsx            Estado vacío con acción
│   ├── EmpleadoDetalleModal.jsx  Ficha del colaborador
│   ├── AsignarPeriodosModal.jsx  Los tres períodos y el cálculo
│   ├── DecisionModal.jsx         Aprobar / rechazar con motivo
│   ├── DescargarPlanillaModal.jsx  Planilla PDF por UNES (Talento Humano)
│   ├── DescargarPlanoModal.jsx   Plano UNOEE general o por UNES
│   └── NuevaAsignacionModal.jsx  Alta de una asignación
├── hooks/useAsignaciones.js      Carga y escritura contre la API
├── layout/AppShell.jsx           Barra superior + sidebar + contenido
├── notifications/
│   ├── NotificacionesProvider.jsx Estado compartido y conteo de pendientes
│   ├── context.js                El contexto (módulo aparte, por Fast Refresh)
│   └── useNotificaciones.js      Hook de acceso con error explícito
├── pages/                        Login, Resumen, Asignaciones,
│                                 Notificaciones, Administración, 404
├── services/
│   ├── api.js                    Cliente HTTP y almacenamiento del token
│   └── navigation.js             Menú, rutas y visibilidad por cargo
├── utils/
│   ├── fechas.js                 Fechas y días (cálculo en UTC)
│   ├── periodos.js               Reglas puras y probadas
│   ├── reporte.js                Generación del CSV (volcado crudo)
│   └── descargas.js              Nombre del archivo y descarga de Blob
└── styles/
    ├── tokens.css                Color, tipografía, espaciado, movimiento
    ├── layout.css                Login, shell, sidebar, topbar y páginas
    └── modal.css                 Modales, formularios, opciones y menú de acciones

tests/periodos.test.mjs           Pruebas de la lógica pura
```

**Reglas del sistema de diseño:** ningún componente escribe un hex ni un valor
de espaciado suelto; todo sale de `styles/tokens.css`. Los números que se
actualizan usan `tabular-nums`. El estado nunca se comunica solo por color
(chip = color + glifo + palabra).

## Pruebas

```powershell
npm test
```

Cubren lo que puede fallar en silencio: conteo de días atravesando meses y años,
febrero bisiesto, rangos invertidos, períodos que se cruzan, el BOM y el escape
del CSV, la neutralización de fórmulas y la lectura del nombre de archivo que
propone el servidor. Son funciones puras, así que corren con `node --test` sin
navegador.

## Accesibilidad

Contraste medido ≥ 4.5:1, foco visible (`:focus-visible`, nunca se elimina),
etiquetas reales asociadas con `htmlFor`, errores junto al campo con
`aria-describedby` y `aria-invalid`, objetivos de 44×44 px, enlace de salto al
contenido, `prefers-reduced-motion` respetado y `aria-live` para anuncios.
