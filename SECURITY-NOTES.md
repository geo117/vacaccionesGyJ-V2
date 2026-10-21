# SECURITY-NOTES.md — Gestión de Vacaciones G&J

Notas de construcción y de seguridad del login, la autenticación y la
validación de datos contra SQL Server.

Alcance de este documento: las decisiones que afectan a la confianza del
sistema —qué se considera confiable, dónde se cruza un límite y qué control lo
detiene—. No es un checklist genérico.

## 1. Límites de confianza

```
Navegador  ──(HTTPS en producción / HTTP en local)──▶  API Flask  ──(TDS)──▶  SQL Server
  no confiable                                          confiable         confiable
```

| Actor | Confianza | Qué aporta |
|---|---|---|
| Navegador / usuario | **No confiable** | Correo, contraseña, encabezado `Authorization`, parámetros de ruta |
| API Flask (backend) | **Frontera de decisión** | Único componente que decide si una credencial es válida y qué puede ver una sesión |
| SQL Server | **Confiable** | Datos de `dbo.Usuarios`; aun así, todo valor que salga de él se normaliza antes de usarse |
| `.env` | **Secreto** | Usuario, contraseña, cadena de conexión y peper de sesión |

Regla que se deriva de esto: **el cliente nunca decide si está autenticado.**
Poseer un token en `sessionStorage` no abre ninguna vista; la aplicación espera
la confirmación del servidor (`GET /api/auth/session`) antes de renderizar
cualquier pantalla interna.

## 2. Superficie expuesta y controles

### 2.1 Inyección SQL — cerrada por construcción

Toda consulta usa parámetros del driver; **ninguna** concatena entrada del
usuario. Los únicos identificadores interpolados en texto son constantes
definidas en `auth.py` y el nombre de tabla `dbo.Usuarios`, que está
calificado con esquema para no depender del usuario por defecto de la base.

```python
# backend/auth.py
_SELECT_USER_BY_EMAIL = (
    "SELECT id, nombre, correo, password_hash, fecha_creacion "
    "FROM dbo.Usuarios WHERE LOWER(correo) = ?"
)
```

Verificado: `backend/test_backend.py` envía `admin@x.com' OR '1'='1`,
`Temporal1' OR 1=1--` y comprueba tanto el rechazo como que la tabla siga
existiendo.

### 2.2 Enumeración de cuentas — cerrada

Correo inexistente, contraseña incorrecta y cuenta sin acceso producen **la
misma** respuesta `401 INVALID_CREDENTIALS` con el mismo texto.

Además, cuando el correo no existe el backend ejecuta igualmente un trabajo
criptográfico completo (`spend_verification_time`), porque un retorno en
microsegundos también revela que la cuenta no existe aunque el mensaje sea
idéntico. La interfaz no reintroduce la diferencia: usa un único mensaje para
todos los fallos de credenciales.

Un fallo de **transporte** no es un fallo de credenciales y queda fuera de esa
respuesta: si la API no responde, tarda de más o un intermediario devuelve un
`5xx` sin cuerpo, el backend no llegó a evaluar la credencial. La interfaz lo
presenta como un problema de comunicación, con texto y tono propios, sin
convertirlo en una pista sobre si la cuenta existe.

### 2.3 Fuerza bruta — acotada

`RateLimiter` (ventana deslizante en memoria, con cerrojo) permite
`LOGIN_MAX_ATTEMPTS2` intentos por **par (IP, correo)** dentro de
`LOGIN_WINDOW_SECONDS2`. La clave combina ambos, de modo que:

* un atacante no puede bloquear la cuenta de otra persona desde otra IP;
* una IP con muchos usuarios legítimos no se bloquea entera.

La respuesta `429` incluye `Retry-After` y un mensaje que informa del límite sin
revelar nada sobre el catálogo de cuentas.

### 2.4 Almacenamiento de contraseñas

| Caso | Tratamiento |
|---|---|
| `scrypt:` / `pbkdf2:` (hash de Werkzeug) | Ruta normal: `check_password_hash` |
| Texto plano heredado | Se compara en tiempo constante (`hmac.compare_digest`) y, **en el mismo inicio de sesión correcto**, se reemplaza por un hash `scrypt` |
| Valor vacío o hash corrupto | Credencial inválida; nunca se propaga un error que revele el contenido de la fila |

Ningún valor en claro se escribe de vuelta. Si el re-hash falla (permisos,
bloqueo), el inicio de sesión sigue siendo válido y solo se registra el
problema: la indisponibilidad de una escritura no debe dejar fuera a alguien con
credenciales correctas.

`HASH_COLUMN_MAX_LENGTH` replica el ancho real de `Usuarios.password_hash`
(`VARCHAR(255)`); si un hash no cupiera, `hash_password` falla en lugar de
truncar silenciosamente un valor que dejaría de verificar.

### 2.5 Gestión de sesión

* Token opaco de 256 bits (`secrets.token_urlsafe(32)`).
* En memoria del proceso solo se guarda `SHA-256(peper ‖ token)`: un volcado de
  memoria no entrega tokens utilizables.
* La comparación del digest se hace en tiempo constante.
* Doble caducidad: absoluta (`SESSION_TTL_SECONDS2`) e inactividad
  (`SESSION_IDLE_SECONDS2`).
* `POST /api/auth/logout` revoca el token en el servidor; el cliente limpia su
  estado incluso si esa llamada falla.
* Techo de sesiones simultáneas (`MAX_SESSIONS`); al alcanzarlo se descarta la
  más antigua en lugar de crecer sin límite.

**Transporte: encabezado `Authorization: Bearer`, no cookie.** Es una decisión
deliberada: sin cookies no existe CSRF posible, no hace falta un token
anti-CSRF y el navegador no adjunta la credencial por su cuenta a peticiones
que el usuario no pidió.

En el cliente el token vive en **`sessionStorage`**, no en `localStorage`:
muere al cerrar la pestaña y no queda disponible durante semanas para cualquier
documento del mismo origen.

### 2.6 CORS

Lista exacta de orígenes (`CORS_ORIGINS2`), `supports_credentials=False` y
`allow_headers` reducido a `Authorization` y `Content-Type`. El arranque
**rechaza** la configuración si contiene `*`: un comodín con credenciales
permitiría a cualquier sitio leer el token de una sesión.

En desarrollo, además, el proxy de Vite (`vite.config.js`) hace que el
navegador solo hable con su propio origen, así que CORS ni se activa.

### 2.7 Validación de entrada

`backend/security.py`:

* Correo: normalizado a minúsculas, `strip()`, tope de 150 caracteres (el ancho
  real de la columna) y patrón sin espacios ni `@` múltiples.
* Contraseña: entre 8 y 128 caracteres, **sin espacios en los extremos** (casi
  siempre es un error de copiado, y decirlo evita un fallo incomprensible) y sin
  caracteres de control.
* Deliberadamente **no** se impone un alfabeto mínimo a la contraseña: esas
  reglas pertenecen al momento de creación, no al de verificación. Aplicarlas
  aquí solo rompería inicios de sesión legítimos.
* Cuerpo JSON obligatorio (`is_json`) con `MAX_CONTENT_LENGTH` de 32 KB.
* `PASSWORD_MAX_LENGTH` acota el trabajo criptográfico: sin tope, una
  "contraseña" de varios megabytes es un DoS de CPU.

### 2.8 Configuración y secretos

| Control | Implementación |
|---|---|
| Credenciales fuera del repositorio | `.gitignore` en la raíz ignora `backend/.env` y permite `backend/.env.example` |
| Arranque con configuración incompleta | `load_settings` lanza `ConfigError` y el proceso sale con código 2 en lugar de usar un valor por defecto silencioso |
| Depurador desactivado | `DEBUG2=True` **impide arrancar**: el depurador de Werkzeug ejecuta código arbitrario desde el navegador |
| Peper de sesión | Obligatorio, mínimo 32 caracteres, con el comando de generación en el mensaje de error |
| `HOST2` por defecto | `127.0.0.1`: la API no se publica a la red salvo que se pida explícitamente |
| Cifrado de la conexión | `DB_ENCRYPT2=yes` por defecto |

Los errores de conexión registran solo el destino (`servidor/base`) y la clase
de excepción; nunca el usuario, la contraseña ni el texto del driver.

### 2.9 Respuestas y cabeceras

Todas las respuestas llevan:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Cross-Origin-Resource-Policy: same-site
Cross-Origin-Opener-Policy: same-origin
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'
Cache-Control: no-store
```

`Cache-Control: no-store` evita que una respuesta con token quede en cachés
intermedias. Los manejadores de error devuelven `{ ok: false, code, message }`
con un `code` estable para el programa y un `message` escrito para la persona;
el detalle de la excepción solo va al log del servidor.

### 2.10 Superficie del frontend

* Sin `dangerouslySetInnerHTML` en ningún componente.
* Sin `innerHTML`, `eval` ni construcción dinámica de URLs: la base de la API
  sale de `import.meta.env.VITE_API_BASE_URL` y `fetch` usa `redirect: 'error'`,
  `referrerPolicy: 'no-referrer'` y `credentials: 'omit'`.
* React escapa todo lo que se interpola; no hay ruta donde el contenido de la
  base se renderice como HTML.
* La contraseña se limpia del estado tras cada fallo y el foco vuelve al campo
  con problema.
* El aviso de comunicación se decide por el código de transporte/HTTP
  (`NETWORK_ERROR`, `TIMEOUT` o `HTTP_5xx` sin el `code` del backend), nunca por
  el resultado de la validación. Un `401 INVALID_CREDENTIALS` sigue siendo
  indistinguible entre cuenta inexistente, contraseña incorrecta y cuenta
  inactiva.
* Accesibilidad como control de calidad, no como adorno: contraste medido ≥
  4.5:1, foco visible (`:focus-visible`, nunca `outline: none`), etiquetas
  reales, errores junto al campo con `aria-describedby`/`aria-invalid`,
  objetivos de 44×44 px, `prefers-reduced-motion` respetado y estado nunca
  comunicado solo por color (chip = color + glifo + palabra).

## 3. Limitaciones conocidas

Se enumeran porque condicionan el despliegue; ninguna se resuelve escribiendo
código en esta iteración.

1. **Sesiones en memoria.** Se pierden al reiniciar el proceso y no se comparten
   entre *workers*. Con `gunicorn -w 4` cada worker tendría su propio almacén y
   una sesión válida fallaría 3 de cada 4 veces. Antes de escalar hay que mover
   el almacén (tabla de sesiones con el hash del token, o Redis).
2. **Limitador de intentos por proceso.** Mismo problema: `LOGIN_MAX_ATTEMPTS2`
   se multiplica por el número de workers. Con varios procesos hay que
   centralizarlo.
3. **`TrustServerCertificate=yes` en las dos conexiones.** Es correcto contra
   `.\\SQLEXPRESS` local con certificado autofirmado, pero la conexión
   corporativa (`DB_*`, vista `PBI_Colaborador_Vacaciones`) apunta a un servidor
   remoto y el `.env` no declara `DB_TRUST_SERVER_CERT`, así que toma el valor
   por defecto `yes`: el canal se cifra, pero no se comprueba con quién se
   habla. Antes de llevarlo a producción hay que poner `DB_TRUST_SERVER_CERT=no`
   (y `DB_TRUST_SERVER_CERT2=no`) con un certificado emitido por una CA en la
   que el cliente confíe.
4. **Sin TLS.** En desarrollo la API viaja por HTTP en loopback. Publicar
   `HOST2=0.0.0.0` sin TLS expone las contraseñas en texto plano a la red local.
5. **Sin cabecera HSTS.** No tiene sentido sin TLS; se añade junto con el
   despliegue HTTPS.
6. **Sin auditoría persistente.** Hoy solo hay log de aplicación. Un requisito
   de trazabilidad de accesos necesita una tabla de auditoría (quién, cuándo,
   desde dónde, resultado) — y esa tabla no debe guardar la contraseña ni el
   token.
7. **`debug=False` no es un servidor de producción.** El servidor incluido de
   Werkzeug es mono-proceso y no está endurecido. El despliegue real va detrás
   de un WSGI (waitress en Windows, gunicorn detrás de Nginx en Linux) con los
   puntos 1 y 2 resueltos.
8. **La conexión corporativa usa `sa`.** Leer una vista no requiere un
   administrador del servidor: mientras `DB_USER` siga siendo `sa`, cualquier
   error de consulta se ejecuta con el máximo privilegio y no tiene red de
   seguridad en la base. Debe ser un usuario con `SELECT` sólo sobre
   `BD_Integraciones.dbo.PBI_Colaborador_Vacaciones`.

## 4. Verificación ejecutada

`backend/test_backend.py` corre 39 comprobaciones contra la base real y las
aprueba todas: validación de entrada, intentos de inyección, credenciales
inexistentes, login correcto, re-hash del valor heredado, ciclo de vida del
token, revocación, rutas y límite de intentos.

```powershell
cd backend
python test_backend.py
cd ..\frontend
npm run lint     # sin errores
npm run build    # sin errores
```

Además se inspeccionó el flujo real en navegador headless sobre el build de
producción (acceso, resumen, asignaciones, notificaciones y ancho móvil de
390 px).

El cambio de mensajes de comunicación de `frontend/src/pages/LoginPage.jsx` se
validó con `npx eslint src/pages/LoginPage.jsx` y `vite build` en un directorio
temporal, sin errores.

## 5. Reglas para quien siga construyendo aquí

1. **Toda consulta nueva usa parámetros.** Si hace falta interpolar un
   identificador, valídalo contra un conjunto cerrado de constantes.
2. **Ninguna respuesta incluye `password_hash`, el connection string, el
   usuario de base ni el nombre del servidor.**
3. **Toda ruta nueva que lea o escriba datos va detrás de `@require_auth`.** Las
   únicas rutas públicas son `/api`, `/api/health` y `/api/auth/login`.
4. **Los roles se leen de la base, no del cliente.** Nunca aceptes un `cargo`,
   `unes` o `rol` enviado por el navegador para decidir qué devolver.
5. **Un error nuevo necesita un `code` estable y un mensaje que no distinga
   "no existe" de "no te corresponde".**
6. **Ningún dato de `mock/` se presenta como real.** Toda vista que use
   `frontend/src/mock` muestra la franja `FixtureNote`.
7. **Al conectar las vistas a datos reales**, reemplaza el import del `mock` y
   elimina los objetos; no los dejes como respaldo silencioso.
