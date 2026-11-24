# Bases de datos de SIRLOD

- `postgres/` contiene el esquema y las migraciones que FastAPI usa para instalar y verificar PostgreSQL.
- `legacy-mysql/` conserva el esquema del padrón anterior. Sus datos y credenciales de recuperación se conservan en el archivo local del proyecto.
- Los respaldos locales con datos permanecen fuera del repositorio, en `SISTEMA_LOSA_backups`. Aplica las migraciones desde la raíz del repositorio con las herramientas de consola.

## Instalación de SIRLOD

El esquema activo en Supabase es `sirlod`. La cuenta de PostgreSQL de FastAPI tiene acceso limitado a ese esquema. Las reservas, las cuentas habilitadas y el padrón local de referencia están en la misma instalación. Las claves de Storage se mantienen para preservar el acceso a los documentos y reportes existentes.

Si la base contiene registros de ejemplo, configura `SIRLOD_DATA_ORIGIN=example`. Esto mantiene los conjuntos de evaluación diferenciados del historial institucional e impide activar un modelo institucional con esos registros. Las credenciales locales se conservan en `database/.env.practice-access`, excluido de Git.

Usa estas dos terminales para abrir SIRLOD en `http://localhost:5174`.

```powershell
# Desde backend_fastapi
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 3005 --reload
```

```powershell
# Desde frontend
npm run dev
```

Para el padrón local usa `UNHEVAL_SOURCE=postgresql` y `UNHEVAL_POSTGRES_VIEW=sirlod.vista_usuario`. Al integrar la universidad, cambia a `UNHEVAL_SOURCE=http` y configura `UNHEVAL_API_URL` con la URL autorizada. El adaptador consulta los datos de identidad por código. Las reservas, asistencias y demás operaciones permanecen en PostgreSQL de SIRLOD.

La operación de consolidación para instalaciones antiguas está en `postgres/maintenance/consolidar_sirlod.sql`. Debe ejecutarse después de verificar un respaldo restorable y en coordinación con el cambio de esquema en FastAPI. Para una instalación nueva con datos de referencia, el aprovisionamiento existente se ejecuta con `.\.venv\Scripts\python.exe -m scripts.seed_practice`.

## Despliegue en Vercel

En Vercel, el frontend SSR usa `frontend/` como **Root Directory**, con la compilación `pnpm run build`. Configura `API_SERVER_URL` con la URL HTTPS de FastAPI terminada en `/api` y `SESSION_SECRET` con una clave propia del entorno. El navegador usa `/api/servicio` para las operaciones directas y la sesión comparte el origen del frontend. [React Router en Vercel](https://vercel.com/docs/frameworks/frontend/react-router)

FastAPI usa `backend_fastapi/` como raíz de su servicio, con `app/main.py` como punto de entrada. Configura la conexión de Supabase mediante **Session pooler**, `POSTGRES_TLS_VERIFY=true` y `POSTGRES_TLS_CA_PEM` con el texto del certificado CA. Configura también Storage, los secretos de sesión y el origen autorizado desde las variables del servicio. Los SQL y respaldos quedan fuera de las raíces de ambos servicios. Ejecuta las migraciones por separado desde una máquina con acceso al repositorio. El entrenamiento sigue siendo una tarea de consola. [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi) · [Conexiones de PostgreSQL en Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)

Para funciones con el límite estándar de 4,5 MB por solicitud, configura `VITE_MAX_UPLOAD_MB=4` en el frontend. Así los formularios declaran un límite que deja espacio para la envoltura multipart. Si el sitio requiere conservar la carga de PDF de hasta 10 MB, el entorno publicado necesita un límite de plataforma suficiente o un flujo de carga directa. Comprueba también el tamaño del paquete de FastAPI con sus dependencias de machine learning. [Límites de Vercel Functions](https://vercel.com/docs/functions/limitations)

En las URLs definitivas, verifica el inicio de sesión, la descarga de PDF, las imágenes y el acceso a Supabase desde ambos servicios.
