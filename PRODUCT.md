# PRODUCT.md — Gestión de Vacaciones G&J

## What this is

An internal web tool for **G&J** that replaces a spreadsheet-driven vacation
workflow. Human Resources (Talento Humano) and UNES leads review vacation
assignments ("asignaciones") per employee, act on them, and receive
notifications. The system is used during a work shift, on desktop, at a desk,
with a second screen sometimes — never on a phone, though it must not break
there.

The single source of operational truth is a **local Microsoft SQL Server**
database (`vacacionesgyj`), already populated and owned by an existing
corporate process. This project does not own that data; it reads and writes it
under the same rules the existing processes use.

## Who uses it

| Role | What they need | What success looks like |
|---|---|---|
| **Talento Humano** (`cargo = 'Talento Humano'`) | See every pending assignment, approve or reject with a motive, notify the area lead | Zero spreadsheet handoffs; every decision carries an audit trail |
| **Gerente UNES** (`cargo = 'gerente unes'`) | See only their UNES, act on the assignments routed to them | No cross-area exposure; no surprises at payroll cutoff |
| **Soporte / Admin** | Access is granted in the database, never in the UI | No self-service role escalation from the interface |

Roles are **data**, not UI state. `users.cargo` and `users.unes` decide what a
session may see. The interface reflects that authority; it never grants it.

## Hard constraints

1. **Credentials live in the database, not in the code.** Passwords are
   verified against `users.password`, which currently holds two generations of
   values: Werkzeug `scrypt` hashes (current) and legacy plaintext (an
   inherited backfill that is being retired). Both must verify; every
   successful legacy login is transparently re-hashed, and no legacy value is
   ever echoed back.
2. **The backend is the only thing that talks to SQL Server.** The browser
   never receives a connection string, a driver name, a server name, or a raw
   password column.
3. **Credentials never enter the repository.** `backend/.env` is read at
   runtime; it is not imported into source, not logged, and not sent to the
   client.
4. **`DEBUG` stays off.** Werkzeug's debugger executes arbitrary code from the
   browser; it is disabled in config and cannot be enabled by an environment
   variable that ships enabled.
5. **Accessibility is not optional.** Corporate deployments include users on
   screen readers and keyboard-only navigation. WCAG 2.1 AA is the floor for
   contrast, focus visibility, and form semantics.

## Functional scope (this iteration)

- **Login** — corporate email + password, verified against SQL Server, with a
  server-issued opaque session token.
- **Home** — a top navbar and a left sidebar with three options:
  1. **Resumen** (dashboard): assignment KPIs and recent activity.
  2. **Asignaciones**: searchable/filterable assignment table.
  3. **Notificaciones**: notification feed with unread state.

Data shown before real endpoints are wired to a given panel comes from
`frontend/src/mock/` — clearly-labelled fixtures, never fabricated database
rows, and never a substitute for a real authorization check.

## Out of scope

Public sign-up, password reset by email, self-service profile editing, and any
change to the SQL Server schema that the corporate process did not sanction.
The one additive object this project introduces is the `auth_sessions` table
(server-side session storage); it is created idempotently and touches nothing
else.

## Voice

Precise, administrative, calm. Colombian Spanish (es-CO) in the interface.
Dates read `dd/mm/aaaa`. No exclamation marks, no marketing tone, no
"¡Bienvenido de vuelta!" enthusiasm for a compliance tool. Errors state what
happened and what to do next, in the same register.
