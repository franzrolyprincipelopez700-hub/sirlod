-- Tras respaldar y restaurar de prueba los tres esquemas, ejecutar como su propietario.
-- El esquema anterior queda en resguardo hasta validar el nuevo servicio.
BEGIN;
SET LOCAL lock_timeout = '8s';
SELECT pg_advisory_xact_lock(11620017);

DO $$
BEGIN
    IF to_regclass('sirlod.users') IS NULL
        OR to_regclass('sirlod_practica.users') IS NULL
        OR to_regclass('padron_practica.vista_usuario') IS NULL
        OR to_regnamespace('sirlod_resguardo') IS NOT NULL THEN
        RAISE EXCEPTION 'Los esquemas no coinciden con la instalación pendiente de consolidar';
    END IF;

    IF has_schema_privilege('sirlod_practica_app', 'sirlod', 'USAGE')
        OR has_schema_privilege('sirlod_practica_app', 'padron_unheval', 'USAGE')
        OR NOT has_schema_privilege('sirlod_practica_app', 'sirlod_practica', 'USAGE') THEN
        RAISE EXCEPTION 'Los permisos del servicio no aíslan su historial correctamente';
    END IF;
END
$$;

ALTER SCHEMA sirlod RENAME TO sirlod_resguardo;
ALTER SCHEMA sirlod_practica RENAME TO sirlod;

ALTER TABLE padron_practica.facultad SET SCHEMA sirlod;
ALTER TABLE padron_practica.escuela_profesional SET SCHEMA sirlod;
ALTER TABLE padron_practica.alumno SET SCHEMA sirlod;
ALTER TABLE padron_practica.docente SET SCHEMA sirlod;
ALTER TABLE padron_practica.personal_administrativo SET SCHEMA sirlod;
ALTER VIEW padron_practica.vista_usuario SET SCHEMA sirlod;
DROP SCHEMA padron_practica;

COMMENT ON SCHEMA sirlod IS 'Datos operativos de referencia de SIRLOD. Origen de ejemplo.';
REVOKE ALL ON SCHEMA sirlod_resguardo FROM PUBLIC, sirlod_practica_app;

DO $$
BEGIN
    IF NOT has_schema_privilege('sirlod_practica_app', 'sirlod', 'USAGE')
        OR NOT has_table_privilege('sirlod_practica_app', 'sirlod.vista_usuario', 'SELECT')
        OR has_table_privilege('sirlod_practica_app', 'sirlod.alumno', 'UPDATE')
        OR has_schema_privilege('sirlod_practica_app', 'sirlod_resguardo', 'USAGE') THEN
        RAISE EXCEPTION 'La validación de acceso del esquema consolidado falló';
    END IF;
END
$$;

COMMIT;
