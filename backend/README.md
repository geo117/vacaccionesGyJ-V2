# Backend — API de autenticación

API HTTP en Flask que valida credenciales contra SQL Server y expone los
endpoints que consume el frontend en React.

## Requisitos

* Python 3.11 o superior (probado en 3.14).
* **Microsoft ODBC Driver 17 for SQL Server** instalado.
* Acceso de lectura/escritura a `dbo.Usuarios` con el login de base configurado.
* Paquetes: `flask`, `flask-cors`, `pyodbc`, `python-dotenv`, `reportlab` y
  `openpyxl` (estos dos últimos sólo para las descargas).

```powershell
python -m pip install flask flask-cors pyodbc python-dotenv reportlab openpyxl
```

## Configuración

1. Copia la plantilla:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Completa el archivo `.env`. Las variables y su efecto:

   | Variable | Para qué sirve |
   |---|---|
   | `DB_SERVER2` | Servidor, por ejemplo `.\SQLEXPRESS` |
   | `DB_NAME2` | Base de datos, por ejemplo `BD_Integraciones` |
   | `DB_USER2` / `DB_PASSWORD2` | Login de SQL Server que usa la API |
   | `DB_DRIVER2` | Driver ODBC, entre llaves |
   | `DB_ENCRYPT2` / `DB_TRUST_SERVER_CERT2` | Cifrado y validación del certificado |
   | `DB_TIMEOUT_SECONDS2` | Tiempo máximo por consulta |
   | `HOST2` / `PORT2` | Dónde escucha la API (`127.0.0.1` = solo esta máquina) |
   | `DEBUG2` | **Debe quedar en `False`**; el depurador de Werkzeug ejecuta código arbitrario desde el navegador |
   | `CORS_ORIGINS2` | Orígenes exactos autorizados; nunca `*` |
   | `SESSION_TTL_SECONDS2` / `SESSION_IDLE_SECONDS2` | Caducidad absoluta y por inactividad |
   | `SESSION_PEPPER2` | Obligatorio, ≥ 32 caracteres |
   | `LOGIN_MAX_ATTEMPTS2` / `LOGIN_WINDOW_SECONDS2` | Límite de intentos por (IP, correo) |

3. Genera el peper de sesión:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Si `SESSION_PEPPER2` falta o es corto, el backend **no arranca** y te dice
   exactamente qué hacer. Es intencional: un peper vacío convierte el hash del
   token en algo trivialmente reversible.

## Tablas que usa la aplicación

```sql
CREATE TABLE dbo.Usuarios (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL,
    correo        VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    fecha_creacion DATETIME DEFAULT GETDATE(),
    cargo         VARCHAR(60) NULL,       -- 'admin' administra cuentas y opera como Talento Humano; 'talento humano' aprueba
    activo        VARCHAR(10) NULL        -- 'si' / 'no': si no está activo, no puede entrar
);
```

`password_hash` debe contener un hash de Werkzeug (`scrypt:` o `pbkdf2:`). Los
valores en texto plano se aceptan para no dejar fuera a las cuentas heredadas y
se re-hashean solos en el primer inicio de sesión correcto.

**Sobre `activo`:** la columna es `VARCHAR(10)` y en la base convive con `'si'`,
`'no'` y valores escritos a mano. El backend acepta un conjunto amplio de formas
afirmativas (`si`, `sí`, `s`, `1`, `true`, `verdadero`, `yes`, `y`, `activo`) y
**trata como inactivo cualquier cosa que no reconozca, incluido `NULL`**. Es
deliberado: ante la duda no se deja entrar a nadie. Al activar o desactivar se
escribe `'si'` o `'no'`, así que esos dos valores son los que verás si lo haces
desde la aplicación.

```sql
CREATE TABLE dbo.asignacion_vacaciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    identificacion VARCHAR(50) NOT NULL,
    empleado VARCHAR(150) NOT NULL,
    cargo VARCHAR(100) NULL,
    desc_unes VARCHAR(255) NULL,
    unes VARCHAR(10) NULL,
    correo VARCHAR(150) NULL,
    estado_asignacion VARCHAR(50) NULL,
    -- OJO: no guarda el corte de la vista, sino el RESULTADO de
    -- «corte − total_dias_empleado». Por eso es decimal y no entero.
    dias_a_corte DECIMAL(6,1) NULL,
    observaciones TEXT NULL,
    periodo1_fecha1 DATE NULL, periodo1_fecha2 DATE NULL, periodo1_dias1 INT NULL,
    periodo2_fecha1 DATE NULL, periodo2_fecha2 DATE NULL, periodo2_dias2 INT NULL,
    periodo3_fecha1 DATE NULL, periodo3_fecha2 DATE NULL, periodo3_dias3 INT NULL,
    -- Decisión individual del período: 'aprobada', 'rechazada' o NULL.
    aprobacion_rechazo_f1 VARCHAR(50) NULL,
    aprobacion_rechazo_f2 VARCHAR(50) NULL,
    aprobacion_rechazo_f3 VARCHAR(50) NULL,
    fecha_regreso DATE NULL,
    -- Fecha de reintegro a labores elegida al crear la asignación; no se deriva
    -- de los períodos y puede diferir de fecha_regreso.
    fecha_reintegro_lab DATE NULL,
    total_dias_empleado INT NULL,
    motivo_rechazo TEXT NULL,
    th_asignacion VARCHAR(100) NULL,
    fecha_registro DATETIME NULL,
    fecha_update DATETIME NULL
);

CREATE TABLE dbo.notificaciones (
    id INT IDENTITY(1,1) PRIMARY KEY,
    unes VARCHAR(50) NULL,
    msj_notificacion TEXT NOT NULL,
    fecha_registro DATETIME DEFAULT GETDATE(),
    fecha_update DATETIME DEFAULT GETDATE(),
    usuario_id INT NULL   -- quién hizo la acción; relaciona con dbo.Usuarios
);
```

### `dias_a_corte` guarda el resultado, no el corte

El nombre engaña: la columna **no** contiene el corte de la vista, sino el
resultado de `corte − total_dias_empleado`. El corte original vive en la vista
corporativa, que es su fuente autoritativa, y se usa como entrada del cálculo.

El resultado se escribe en la misma operación que crea la asignación y se
**recalcula cada vez que cambian los períodos**. Para recalcularlo, el corte se
despeja del propio valor guardado (`resultado + total`) y se vuelve a aplicar con
el total nuevo; sin ese paso, editar los períodos dejaría el resultado viejo y la
base contradiría a la pantalla.

La columna es `DECIMAL(6,1)` porque el corte de la vista trae un decimal (7.2) y
con `INT` el resultado se truncaba en silencio.

### Los días se cuentan sin domingos ni festivos

Un domingo o un festivo dentro de un período no se disfruta como vacaciones, así
que no suma al total. Esa lista de fechas inactivas vive en
**`backend/fechas_inactivas.json`** y es la **fuente única** para todo el
sistema:

* el backend la lee en `dias_inhabiles.py` y la aplica en `normalizar_periodos`
  (de ahí salen `periodo*_dias*`, `total_dias_empleado` y `dias_a_corte`);
* la interfaz la importa en `frontend/src/hooks/fechas_inactivas.js`, y con ella
  previsualiza los mismos días en los modales de alta, edición, detalle y
  decisión.

Si la lista estuviera duplicada, la pantalla y la base podrían calcular totales
distintos para las mismas fechas. Para agregar un festivo se edita el JSON y se
**reinicia el backend**: la lista se cachea al primer uso para no leer el archivo
en cada petición. `test_backend.py` comprueba un caso fijo (diciembre de 2026:
25 días de 31).
```

La tabla es "aplanada" (los tres períodos en columnas), pero la API trabaja con
una lista de períodos y `assignments.py` traduce en los dos sentidos para que el
resto del sistema no sepa de esa forma.

Para crear una cuenta con la contraseña ya hasheada:

```python
from security import hash_password
print(hash_password("la-contrasena-temporal"))
```

## Cómo ejecutarlo

```powershell
python app.py
```

En el arranque se registra el destino (`servidor/base`), nunca el usuario ni la
contraseña. El servidor incluido de Flask es para desarrollo: ver la sección de
limitaciones en `../SECURITY-NOTES.md` antes de desplegar.

## Endpoints

Todas las rutas de datos exigen `Authorization: Bearer <token>`. La columna
**Quién** indica el cargo necesario; el control se aplica en el servidor, no en
la interfaz.

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| `GET` | `/api` | Público | Índice del servicio |
| `GET` | `/api/health` | Público | Estado de la API y de las tres tablas |
| `POST` | `/api/auth/login` | Público | Valida credenciales y emite el token. La UNES es opcional para Talento Humano y admin |
| `POST` | `/api/auth/logout` | Sesión | Revoca el token actual |
| `GET` | `/api/auth/session` | Sesión | Confirma la sesión y devuelve el usuario con su cargo |
| `GET` | `/api/resumen` | Sesión | Totales de la empresa para Talento Humano y admin; los de la UNES de la sesión para el resto |
| `GET` | `/api/asignaciones` | Sesión | Colaboradores de la UNES de la sesión; **toda la plantilla de su empresa** para Talento Humano y **la de todas las empresas** para el admin. Los correos de `data colmena/colmena.json` reciben sólo las cédulas de su equipo; la dirección, la unión de sus propias entradas en `colmena.json` y `filial.json`. Para Talento Humano y el admin incluye `areas` y el `area` de cada fila (GyJ: `data filial/areas_filial.json`; Colmena: `data colmena/areas_colmena.json`) |
| `GET` | `/api/asignaciones/{id}` | Sesión | Una asignación |
| `POST` | `/api/asignaciones` | Sesión | Registra una asignación nueva |
| `PUT` | `/api/asignaciones/{id}/periodos` | Sesión | Programa los tres períodos |
| `POST` | `/api/asignaciones/{id}/decision` | **Talento Humano o admin** | Aprueba o rechaza la asignación completa (todos los períodos) |
| `POST` | `/api/asignaciones/{id}/periodos/{n}/decision` | **Talento Humano o admin** | Aprueba o rechaza un período concreto y recalcula el estado |
| `GET` | `/api/reportes/planilla` | Sesión | Planilla de vacaciones en PDF (plantilla institucional). Filtra por la UNES pedida (`?unes=`) o por la de la sesión. Quien entra con UNES sólo puede generarla cuando todas las vacaciones de su UNES están aprobadas |
| `GET` | `/api/reportes/plano-unoee` | **Talento Humano o admin** | Plano UNOEE en Excel sobre la plantilla oficial |
| `GET` | `/api/notificaciones` | Sesión | Bandeja del cargo: Talento Humano y admin ven todas; los demás, las de la UNES de su sesión |
| `GET` | `/api/notificaciones/mias` | Sesión | Avisos generados por quien consulta (`usuario_id`) |
| `GET` | `/api/usuarios` | **Admin** | Usuarios registrados, con su estado |
| `POST` | `/api/usuarios` | **Admin** | Crea un usuario |
| `PUT` | `/api/usuarios/{id}` | **Admin** | Edita nombre, correo, cargo y/o contraseña |
| `PATCH` | `/api/usuarios/{id}/activo` | **Admin** | Activa o desactiva la cuenta |
| `DELETE` | `/api/usuarios/{id}` | **Admin** | Elimina y cierra sus sesiones |

## Las dos conexiones

El backend habla con **dos** bases de datos. En el `.env` conviven con sufijos
distintos y no son intercambiables:

| Prefijo | Para qué | Obligatoria |
|---|---|---|
| `DB_*2` (por ejemplo `DB_SERVER2`) | La base propia: `Usuarios`, `asignacion_vacaciones`, `notificaciones` | Sí, sin ella no arranca |
| `DB_*` (`DB_SERVER`) | La vista corporativa `PBI_Colaborador_Vacaciones_V2` | No |

La segunda es **opcional a propósito**: si el servidor corporativo no responde,
el backend arranca igual y `/api/asignaciones` degrada al listado local de
asignaciones en lugar de dejar la pantalla en blanco. La respuesta lo dice en
`origen` (`"vista"` o `"local"`) y la interfaz lo avisa.

Para Talento Humano y el admin, `/api/asignaciones` anota además cada fila con su
`area` y devuelve la lista `areas`, cruzadas por **cédula**. El archivo depende de
la empresa de la cuenta (`Usuarios.company`):

| `company` | Empresa | Archivo de áreas |
|---|---|---|
| `2` | GyJ Ferreterías | `data filial/areas_filial.json` |
| `3` | Almasa | (sin archivo todavía: no se envía filtro) |
| `4` | Colmena | `data colmena/areas_colmena.json` |

El **admin** ve la plantilla de las dos empresas que tienen archivo, así que
recibe las dos listas unidas en el mismo desplegable. El resto de cargos no
recibe ese dato ni el filtro en la pantalla.

`/api/health` informa del estado de las dos:

```json
{"db":"ok","directorio":"ok","ok":true,"version":"2.0.0"}
```

### La conexión corporativa es de sólo lectura

Sobre esa vista **no se escribe nunca**: todas las consultas son `SELECT`. Es una
vista mantenida por otro proceso y no nos pertenece.

Dos advertencias que conviene tener presentes:

* Las credenciales que trae el `.env` son de un usuario **`sa`** (administrador
  del servidor). Para leer una vista no hace falta ese poder: lo correcto es un
  usuario con `SELECT` sólo sobre esa vista. Mientras siga siendo `sa`, un error
  en cualquier consulta no tiene red de seguridad en la base.
* `DB_TRUST_SERVER_CERT` está en `yes`, así que la conexión cifra pero **no
  valida el certificado del servidor**: acepta cualquiera. En una red interna es
  el compromiso habitual; si el tráfico sale de la red, hay que ponerlo en `no` y
  confiar en el certificado real.

## La empresa de la cuenta

`dbo.Usuarios.company` guarda a qué empresa pertenece cada cuenta. Se elige en el
modal de Administración y no se puede escribir un valor libre: el backend sólo
acepta los del catálogo.

| `company` | Empresa | Prefijo de `IDCia_CO` |
|---|---|---|
| `2` | GyJ Ferreterías | `2-…` |
| `3` | Almasa | `3-…` |
| `4` | Colmena | `4-…` |

La vista `PBI_Colaborador_Vacaciones_V2` reúne la plantilla de las tres empresas.
El **primer dígito** de `IDCia_CO` identifica la empresa (`'4-301'` → `4`), así
que el servidor lo compara en el `WHERE` con la empresa de la sesión. Una cuenta
de Colmena nunca recibe por la API la plantilla de GyJ ni la de Almasa, ni
siquiera cuando la vista corporativa falla y se degrada al listado local: el
registro guarda la UNES completa (`'4-301'`) y permite aplicar el mismo filtro.

La única excepción es el **admin**: su cargo implica ver toda la información de
los colaboradores del grupo, así que su tablero y su planilla **no se acotan por
empresa** (`empresa_para_tablero()` devuelve `0`, que en el directorio significa
"sin filtro"). Sí sigue acotado por UNES cuando pide una concreta.

Las cuentas anteriores a la columna (o con el valor vacío) se asumen de GyJ
(`2`), que es la empresa para la que nació la aplicación. Cambiar la empresa de
un usuario surte efecto en su siguiente petición: `authenticate` vuelve a leer
la fila en cada llamada.

## El filtro por UNES

La UNES se **digita en el login** y no se guarda en `dbo.Usuarios`: vive en la
sesión. Se aceptan `109` y `2-109`.

**Talento Humano y el admin entran sin UNES.** El tablero de Talento Humano es la
plantilla completa **de su empresa** y el del admin, la de **todas las empresas
del grupo** (`EmployeeDirectory.listar_todos`), así que el campo es opcional para
esos cargos: si las credenciales son correctas y no se envió UNES, la sesión se
emite con `unes` vacío. Los **jefes de Colmena** también entran sin UNES: su
alcance sale de `data colmena/colmena.json`, no de una unidad digitada. Para
cualquier otro cargo la UNES es obligatoria, porque su listado se filtra por
ella; si falta, el login responde `400 UNES_REQUERIDA` **después** de comprobar
la contraseña, no antes. Cuál de las dos cosas aplica lo decide el `cargo` (y el
correo) que están en la base, nunca un valor de la petición.

El filtro se aplica en el `WHERE` de SQL, comparando los **tres últimos dígitos**
de `IDCia_CO`, y acota **las dos** cosas: los colaboradores de la vista y las
asignaciones huérfanas (las de alguien que ya no está en la plantilla). Filtrar
sólo lo primero dejaría ver movimientos de otras UNES por esa puerta.

No es cosmético: es una regla de acceso. Un usuario no debe recibir por la API
la plantilla de otras UNES, así que el filtro no puede hacerse en el navegador.
Talento Humano es la excepción declarada: su cargo implica ver toda la plantilla
de **su empresa**. El admin va un paso más allá y ve la de **todas las empresas**.

## Los jefes de Colmena

`data colmena/colmena.json` asocia cada correo de jefe con las cédulas de su
equipo. Es un alcance **independiente de la UNES**: estas cuentas entran sin
digitarla y el servidor acota el tablero por la **cédula**
(`identificacion`), que es la llave que comparte con la vista corporativa.

| Regla | Comportamiento |
|---|---|
| Empresa de la cuenta | Debe ser `company = 4` (Colmena). Si las credenciales son correctas pero la cuenta es de otra empresa, el login responde `INVALID_CREDENTIALS` sin revelar el motivo. |
| UNES | No se valida ni se usa. Si se escribe algo, se ignora. |
| Alcance | Sólo las cédulas de la lista de ese correo. |
| Sábado | `SABADO HABIL`: `SI` cuenta el sábado como vacaciones; `NO` lo descuenta. |
| Dirección del grupo | `director.riesgos@gyj.com.co`, `direcciontic@gyj.com.co` y `direccion_th@gyj.com.co` ven la **unión de sus propias entradas** en `colmena.json` y `filial.json` (las cédulas registradas a nombre de ese correo), sin importar la empresa de la cuenta. |
| Caché | El archivo se lee una vez; si se edita, hay que reiniciar el backend. |

El filtro se aplica en el servidor (una fila que no sea de la lista no llega al
navegador). El tablero sólo lo refleja y lo anuncia en `alcanceColmena`
(`equipo` o `grupo`).

## Los días a usar

`diasAUsar = diasACorte − diasAsignados`, **en ese orden**, calculado en el
servidor y **persistido en la columna `dias_a_corte`**. Así la tabla, los modales,
el reporte y la base no pueden discrepar: lo que se muestra es lo que está
guardado.

El orden no es indiferente: con los días a corte primero, un resultado
**positivo** significa que al colaborador le quedan días por disfrutar sobre lo
programado, y uno **negativo** que programó más días de los que tiene. Sin fechas
programadas el valor es igual a los días a corte.

El semáforo de la interfaz usa estos umbrales: menos de −3 rojo, de −3 a 10
amarillo, más de 10 verde. El color nunca es la única señal: la celda lleva
además la etiqueta para lectores de pantalla y un `title` con la operación.

El mismo número aparece en tres sitios con el mismo cálculo y los mismos tonos:

| Dónde | Cómo se ve |
|---|---|
| Tabla de asignaciones | celda de la columna «A usar» |
| Modal de nueva asignación | «Días a usar» en el resumen, bajo «Total asignado» |
| Modal de edición de períodos | línea «Días a usar» dentro del resumen |

Los días a corte **no se editan** en el modal de nueva asignación: salen de la
vista del colaborador y sólo alimentan el cálculo. Si una fila no los trajera, la
interfaz lo dice en lugar de calcular sobre cero.

### SÁBADO HÁBIL

Cada colaborador de `data colmena/colmena.json` trae el campo `SABADO HABIL`:

| Valor | Cómo se calcula |
|---|---|
| `SI` | El sábado es día hábil: **cuenta** como día de vacaciones. |
| `NO` | El sábado no se trabaja: **se descuenta**, igual que un domingo. |
| Sin dato o cédula fuera del archivo | Se mantiene el cálculo general (el sábado cuenta). |

La regla se aplica en `dias_habiles(..., sabado_habil=...)` al crear y al guardar
períodos, así que el total persistido y el que calcula la interfaz coinciden. Las
filas de `/api/asignaciones` llevan `sabadoHabil` para que el navegador
previsualice con el mismo criterio; el servidor vuelve a recalcular al guardar.

## Plazo de vacaciones colectivas

La fecha límite es el **1 de diciembre de 2026** (`plazos.py`). La interfaz
muestra un aviso con cuenta regresiva desde seis días antes (`2026-11-25`).

Cuando ya pasó el día límite (`2026-12-02` en adelante), el backend aplica una
vez al día el **corte de cuentas**: en cualquier petición a la API se ejecuta
`desactivar_sin_privilegios()`, que pone `activo = 'no'` a todos los usuarios
cuyo `cargo` no sea `admin` ni `talento humano`. Esas cuentas quedan fuera en la
siguiente petición, porque `authenticate` vuelve a leer el estado de la base.
La fecha del corte se decide en el servidor; el navegador sólo muestra el aviso.

## Notificaciones

`dbo.notificaciones` tiene `id`, `unes`, `msj_notificacion`, `usuario_id`,
`fecha_registro` y `fecha_update`. `usuario_id` relaciona con `dbo.Usuarios` y
guarda **el id de quien hizo la acción**: es lo que permite saber quién asignó las
fechas, quién aprobó y quién rechazó, y contar sus avisos pendientes.

Quién ve qué:

| Aviso | Quién lo ve |
|---|---|
| Asignación de fechas, aprobación, rechazo por período, rechazo total, observación | **Talento Humano y admin** (todas) y **los usuarios de la UNES de la asignación** |
| Los que uno mismo generó | Quien los generó, por `usuario_id` (`/api/notificaciones/mias`) |

Cada aviso guarda en la columna **`unes`** la UNES de la asignación (por ejemplo
`2-115`), no la del usuario que actuó. Así la bandeja muestra a qué unidad
corresponde el movimiento aunque lo haya aprobado Talento Humano o el admin.

La tabla **no tiene columna de «leída»**: el conteo de pendientes que muestra el
sidebar lo lleva el navegador (ids ya vistos, por usuario). No es una verdad del
servidor y no se pretende que lo sea; la alternativa sería añadir una columna,
que es una decisión de esquema aparte.

El texto del aviso lo compone **el servidor**, nunca el cliente: si el navegador
mandara el mensaje, cualquiera podría escribir el aviso que quisiera en la
bandeja de los demás.

Si el aviso falla, la acción **no** se deshace: la asignación ya quedó registrada
y perderla por un aviso fallido sería peor. Se deja constancia en el log.

### La suite de pruebas limpia lo que crea

`test_backend.py` borra al terminar la asignación de prueba y **los avisos que
generó**. Si no lo hiciera, cada corrida llenaría la bandeja de notificaciones con
mensajes de prueba, y una bandeja con ruido deja de ser útil para revisar lo que
pasó de verdad.

### Activar y desactivar

`PATCH /api/usuarios/{id}/activo` con `{ "activo": true | false }`.

Desactivar surte efecto **de inmediato**, no cuando caduque el token:

* se cierran las sesiones abiertas de esa persona;
* `AuthService.authenticate` vuelve a comprobar el estado en la base en **cada
  petición autenticada**, así que un token ya emitido deja de servir en el acto.

Esa comprobación cuesta una consulta por petición autenticada. Es el precio de
que el control sea inmediato; si algún día pesa, la alternativa es cachear la
comprobación unos segundos, nunca eliminarla.

Dos protecciones más: no se puede desactivar el propio usuario
(`409 NO_SE_PUEDE_DESACTIVAR_A_SI_MISMO`) ni dejar el sistema sin ningún Talento
Humano activo (`409 ULTIMO_TALENTO_HUMANO`) o sin ningún admin activo
(`409 ULTIMO_ADMIN`). Esa última cuenta sólo los **activos**, así que degradar o
eliminar a alguien ya desactivado no se bloquea.

### El cargo manda

`usuarios.cargo` se lee de la base en cada petición y viaja en la sesión. Las
rutas de administración de usuarios están detrás de `@require_admin`; las de
decisión y plano UNOEE, de `@require_talento_humano`, que acepta tanto el cargo
de Talento Humano como el de admin. Si el cargo no coincide, responden
`403 FORBIDDEN_ROLE`. **Ocultar la opción en el navegador no es el control**;
esto sí lo es, porque a la API se le puede llamar directamente con un token
válido.

El alcance del tablero es otra regla: `ve_toda_la_plantilla` es verdadero para
Talento Humano y para el admin, que entran sin UNES. Talento Humano ve toda su
empresa; el admin, la de todas las empresas del grupo. El resto de cargos sólo ve
su UNES. El admin además hereda `puede_aprobar`, de modo que puede decidir sobre
las asignaciones y generar el plano UNOEE igual que Talento Humano.

Tres protecciones adicionales evitan dejar el sistema sin administración:

* no se puede eliminar el propio usuario (`409 NO_SE_PUEDE_ELIMINAR_A_SI_MISMO`);
* no se puede eliminar ni degradar al último usuario de Talento Humano
  (`409 ULTIMO_TALENTO_HUMANO`);
* no se puede eliminar ni degradar al último admin (`409 ULTIMO_ADMIN`).

### Los días los calcula el servidor

`PUT /api/asignaciones/{id}/periodos` **ignora** cualquier `totalDias` que envíe
el cliente: recalcula los días de cada período (contando ambos extremos) y su
suma. Si se confiara en el número del navegador, cualquiera podría guardar
"0 días" para un período de dos semanas. También rechaza rangos invertidos
(`RANGO_INVERTIDO`) y períodos que se cruzan (`PERIODOS_CRUZADOS`).

### La decisión por período

`POST /api/asignaciones/{id}/periodos/{n}/decision` guarda **en el acto** la
decisión de un período (1 a 3) en `aprobacion_rechazo_f1`...`f3`
(VARCHAR(50)). Los demás períodos conservan lo que ya tenían; al cambiar las
fechas con `PUT /periodos`, las tres columnas se limpian porque la decisión
anterior ya no corresponde a los nuevos períodos. El servidor rechaza con
`PERIODO_SIN_PROGRAMAR` cualquier decisión sobre un período vacío.

El estado de la asignación se deriva de los períodos **programados**:

| Situación | `estado_asignacion` |
|---|---|
| Todos aprobados | `aprobada` |
| Todos rechazados | `rechazada` |
| Hay algún rechazo, pero no todos | `en_verificacion` |
| Sin rechazos y no están todos aprobados | `pendiente` |

`POST /api/asignaciones/{id}/decision` sigue existiendo para la decisión
general: «aprobar» deja todos los períodos programados en `aprobada` y el estado
en `aprobada`; «rechazar» los deja todos en `rechazada`, exige el motivo y deja
el estado en `rechazada`.

Ese mismo endpoint puede recibir `decisionesPeriodos` (una lista de hasta tres
valores `aprobada` / `rechazada` / `null`). Cuando viene, el servidor respeta la
decisión de cada período y **deriva** el estado con la tabla de arriba, en lugar
de aplicar una decisión uniforme. Es lo que permite guardar el motivo de unos
rechazos ya decididos sin aprobar ni rechazar de más los demás períodos: 1
rechazado y 2 aprobados queda en `en_verificacion`. El motivo se exige siempre
que la decisión deje algún rechazo.

En la interfaz, el modal de decisión ofrece «Rechazar todo» (rechaza los tres
períodos y pide un motivo único) y, cuando hay rechazos individuales, un
recuadro con una fila de motivo por período. Al guardar, los motivos se
concatenan en `motivo_rechazo` («Período 1: … | Período 2: …»); con un solo
rechazo se guarda su texto tal cual.

### Migración de bases anteriores

Si la base se creó con una versión anterior del esquema, puede faltar la decisión
por período. El script `migrations/20261108_aprobacion_rechazo.sql` agrega
`aprobacion_rechazo_f1..f3` de forma idempotente (`VARCHAR(50) NULL`). El
diagnóstico `python health.py` avisa si faltan.

### Las notificaciones las redacta el servidor

El aviso se etiqueta con la UNES de la asignación y guarda en `usuario_id` el id
de **quien hizo la acción**. El filtro se aplica en el `WHERE` de la consulta,
nunca en el navegador: Talento Humano y el admin ven la bandeja completa; los
demás cargos ven los avisos de la UNES con la que entraron, y cada quien puede
pedir además los que generó (`/api/notificaciones/mias`).

### `POST /api/auth/login`

```jsonc
// Petición — la UNES es opcional: Talento Humano y el admin entran sin ella
{ "correo": "nombre@gyj.com.co", "password": "…", "unes": "109" }

// 200
{
  "ok": true,
  "token": "…",
  "token_type": "Bearer",
  "expires_in": 28800,
  "usuario": {
    "id": 1,
    "nombre": "…",
    "correo": "…",
    "cargo": "talento humano",
    "esTalentoHumano": true,
    "esAdmin": false,
    "veTodaLaPlantilla": true,
    "puedeAprobar": true,
    "unes": ""
  }
}
```

Respuestas de error — el `code` es estable para el programa; el `message` está
escrito para la persona y **no** distingue si la cuenta existe:

| `code` | HTTP | Cuándo |
|---|---|---|
| `EMAIL_INVALID` | 400 | Correo vacío, demasiado largo o con formato inválido |
| `PASSWORD_INVALID` | 400 | Contraseña vacía, corta o con caracteres de control |
| `PASSWORD_WHITESPACE` | 400 | La contraseña empieza o termina con espacio |
| `PASSWORD_TOO_LONG` | 400 | Supera los 128 caracteres |
| `UNES_INVALIDA` | 400 | La UNES trae algo distinto de tres dígitos (`109`, `2-109`) |
| `UNES_REQUERIDA` | 400 | Credenciales correctas de un cargo que **no** ve toda la plantilla y falta la UNES |
| `INVALID_CREDENTIALS` | 401 | Correo inexistente, contraseña incorrecta o cuenta sin acceso |
| `TOO_MANY_ATTEMPTS` | 429 | Se superó el límite; incluye `Retry-After` |
| `DATABASE_UNAVAILABLE` | 503 | SQL Server no responde |
| `INTERNAL_ERROR` | 500 | Fallo inesperado; el detalle queda solo en el log |

`UNES_REQUERIDA` sólo se responde **después** de verificar las credenciales: quien
no las tenga sigue viendo `INVALID_CREDENTIALS`, así que el error no sirve para
averiguar qué correos existen.

### Rutas autenticadas

```http
Authorization: Bearer <token>
```

Sin encabezado → `401 SESSION_REQUIRED`. Con un token inválido, expirado o
revocado → `401 SESSION_EXPIRED`. El frontend trata ambos casos volviendo al
acceso con un aviso único.

## Pruebas

```powershell
python test_backend.py
```

66 comprobaciones contra la base real: credenciales, **control de rol** (Talento
Humano y otros cargos reciben 403 en las rutas de administración, y el resto en
la de decisión), alta/edición/eliminación de usuarios, persistencia de los tres
períodos, recálculo de días y total, cruces y rangos invertidos, decisiones que
generan notificaciones, resumen y las protecciones del último Talento Humano y
del último admin.

> Deja datos de prueba en la base. Úsala contra una base de desarrollo.

## Estructura

| Archivo | Responsabilidad |
|---|---|
| `app.py` | Rutas, decoradores de rol, manejadores de error, cabeceras, CORS |
| `config.py` | Lectura y validación del entorno; falla al arrancar si algo es inseguro |
| `security.py` | Validación, hash/verificación de contraseñas, tokens y limitador |
| `users.py` | Modelo de usuario, repositorio y reglas del cargo |
| `auth.py` | Almacén de sesiones y servicio de login |
| `assignments.py` | Asignaciones: repositorio, validación y cálculo de días |
| `notifications.py` | Avisos: redacción en el servidor y filtrado por cargo |
| `reports.py` | Planilla en PDF y plano UNOEE en Excel |
| `dashboard.py` | Resumen: totales globales o por UNES y consolidado por empleado (`LEFT JOIN`) |
| `db.py` | Conexión, cursores parametrizados y acceso por nombre de columna |
| `test_backend.py` | Prueba de humo end-to-end |
