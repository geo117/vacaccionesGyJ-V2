-- Edición de fechas después del cierre de vacaciones colectivas.
--
-- Hasta ahora, pasado el 1 de diciembre de 2026 el backend ponía `activo = 'no'`
-- a las cuentas que no fueran admin ni Talento Humano. La regla cambió: las
-- cuentas siguen activas y lo que se deshabilita es la programación de fechas.
--
-- `act_edicion` guarda 'si' o 'no'. Se deja NULL a los cargos sin privilegios
-- para no bloquear la edición antes del plazo: el corte del servidor la pone en
-- 'no' cuando llega la fecha. Admin y Talento Humano quedan en 'si' desde ya.
--
-- Es idempotente: se puede ejecutar varias veces sin error.

IF COL_LENGTH('dbo.Usuarios', 'act_edicion') IS NULL
    ALTER TABLE dbo.Usuarios ADD act_edicion VARCHAR(10) NULL;

UPDATE dbo.Usuarios
SET act_edicion = 'si'
WHERE LOWER(LTRIM(RTRIM(ISNULL(cargo, '')))) IN ('admin', 'talento humano')
  AND (act_edicion IS NULL OR LTRIM(RTRIM(act_edicion)) = '');
