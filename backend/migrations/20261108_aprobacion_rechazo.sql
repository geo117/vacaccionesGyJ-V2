-- Decisión individual de cada período de vacaciones.
--
-- El README define estas columnas desde el diseño original, pero en algunas
-- bases creadas antes de esa versión no existen. Sin ellas, aprobar o rechazar
-- un período (y el nuevo recuadro de motivos) falla con un 500.
--
-- Es idempotente: se puede ejecutar varias veces sin error.

IF COL_LENGTH('dbo.asignacion_vacaciones', 'aprobacion_rechazo_f1') IS NULL
    ALTER TABLE dbo.asignacion_vacaciones ADD aprobacion_rechazo_f1 VARCHAR(50) NULL;

IF COL_LENGTH('dbo.asignacion_vacaciones', 'aprobacion_rechazo_f2') IS NULL
    ALTER TABLE dbo.asignacion_vacaciones ADD aprobacion_rechazo_f2 VARCHAR(50) NULL;

IF COL_LENGTH('dbo.asignacion_vacaciones', 'aprobacion_rechazo_f3') IS NULL
    ALTER TABLE dbo.asignacion_vacaciones ADD aprobacion_rechazo_f3 VARCHAR(50) NULL;
