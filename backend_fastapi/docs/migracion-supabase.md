# Migración de SIRLOD a Supabase

El proyecto de destino usa un esquema privado `sirlod` para la aplicación y uno denominado `padron_unheval` para el catálogo académico. FastAPI puede consultar ambos con la misma conexión. Las sesiones, permisos, reportes y RF-04 a RF-06 se gestionan desde FastAPI. Las llaves de la base y de Storage se guardan localmente en archivos de entorno ignorados por Git.

## Datos de origen y recuperación

El importador lee las cinco tablas del padrón MySQL en una transacción de solo lectura. Con `SIRLOD_SOURCE_DATABASE_URL` restaura también las tablas operativas disponibles del PostgreSQL de origen, incluidos los expedientes y las versiones de aprendizaje. Las sesiones y los tokens de recuperación se crean de nuevo en el destino. Si no se dispone de una conexión a ese PostgreSQL, la migración usa el catálogo, la configuración y las cuentas compatibles con bcrypt de la base local `sistema_losa`. La fuente local verificada tenía 40 personas en el padrón y 5 losas. Los datos iniciales de MySQL se conservan en el respaldo local.

La migración verifica las filas por clave, conserva las identidades, ajusta las secuencias y detiene el bloque de base de datos si encuentra conflicto en el destino. Los archivos S3 se comprueban por SHA-256 y conservan sus claves. Solo se cambian las URLs de los archivos e imágenes reconocidos como parte del bucket de origen.

## Configurar el destino

Crea un proyecto para SIRLOD desde el panel de Supabase. Obtén la cadena PostgreSQL de **Connect → Session pooler**, con su contraseña real. Guarda los valores en `.env.supabase`, en la raíz de este repositorio. El archivo se ignora al versionar.

```dotenv
SUPABASE_DATABASE_URL=postgresql://postgres.REFERENCIA:CONTRASENA@HOST_POOLER:5432/postgres?sslrootcert=C:/ruta/ca-de-supabase.pem
# SIRLOD_SOURCE_DATABASE_URL=postgresql://USUARIO:CONTRASENA@HOST:5432/BASE_ANTERIOR
# SIRLOD_SOURCE_SCHEMA=public
# SUPABASE_STORAGE_URL=https://REFERENCIA.supabase.co
# SUPABASE_STORAGE_SECRET_KEY=CLAVE_DE_SERVIDOR
# SUPABASE_STORAGE_BUCKET=sirlod
```

Codifica los caracteres reservados de la contraseña en la URL y descarga el certificado CA de **Database Settings**. Para mover los objetos, usa una clave de servidor del mismo proyecto en `SUPABASE_STORAGE_SECRET_KEY`. El bucket se crea privado si hace falta y se comprueba antes de copiar. El backend conserva su acceso al bucket de origen durante la transferencia. Como alternativa puedes configurar las variables `SUPABASE_STORAGE_ENDPOINT`, `SUPABASE_STORAGE_REGION`, `SUPABASE_STORAGE_ACCESS_KEY_ID` y `SUPABASE_STORAGE_SECRET_ACCESS_KEY` para usar S3.

## Ejecutar y verificar

```powershell
cd backend_api
npm ci
cd ..\backend_fastapi
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m scripts.migrate_supabase
```

Si Storage ya está configurado, activa la base y los archivos en una ejecución.

```powershell
python -m scripts.migrate_supabase --copy-storage --switch
python -m scripts.check_database
python -m uvicorn app.main:app --host 127.0.0.1 --port 3000
```

Si la base se activa primero, usa `python -m scripts.migrate_supabase --storage-only --copy-storage --switch` para copiar los archivos, comprobarlos y activar Storage.

Con `UNHEVAL_SOURCE=postgresql`, la API de FastAPI consulta el padrón directamente y el flujo de SIRLOD requiere solo FastAPI y el frontend. Verifica `/ready`, el inicio de sesión y el listado de losas antes de habilitar la operación. La primera activación conserva una copia local en `backend_fastapi/.env.pre_supabase`.

## Reiniciar esta instalación local

La instalación local abre una sola aplicación en `http://localhost:5174`, conectada al [perfil de práctica](../../database/README.md). El menú **Analítica** enlaza Demanda de losas, Alertas de actividad y Asistencia y riesgo. La conexión institucional se conserva en `backend_fastapi/.env` y el perfil anterior del frontend en `frontend/.env.institucional` para usarlo cuando corresponda.

Documentación de Supabase. [Migración de PostgreSQL](https://supabase.com/kb/guides/migrate-from-postgres), [conexión PostgreSQL con TLS](https://supabase.com/docs/guides/database/psql) y [claves de Storage y control de acceso](https://supabase.com/docs/guides/storage/security/access-control).

