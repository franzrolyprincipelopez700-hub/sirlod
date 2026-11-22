# Bases de datos de SIRLOD

- `postgres/` contiene el esquema y las migraciones que FastAPI usa para instalar y verificar PostgreSQL.
- `legacy-mysql/` conserva el esquema del padrón anterior. Sus datos y credenciales de recuperación se conservan en el archivo local del proyecto.
- Los respaldos locales con datos permanecen fuera del repositorio, en `SISTEMA_LOSA_backups`. Aplica las migraciones desde la raíz del repositorio con las herramientas de consola.

## Entorno de práctica

En Supabase, `sirlod_practica` y `padron_practica` tienen una cuenta PostgreSQL limitada a esos dos esquemas. El bucket privado `sirlod-practica` contiene sus documentos y reportes. FastAPI firma sus sesiones y artefactos con claves propias. El entrenamiento en este perfil solo admite versiones de práctica.

Desde `backend_fastapi`, aprovisiona con `.\.venv\Scripts\python.exe -m scripts.seed_practice`. La operación conserva los registros existentes si se ejecuta de nuevo. Las cuentas de administración, garita y alumno se guardan en `database/.env.practice-access`. Ese archivo y los perfiles locales quedan ignorados por Git.

Usa estas dos terminales para abrir SIRLOD en `http://localhost:5174`. El perfil local utiliza los datos de práctica.

```powershell
# Desde backend_fastapi
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 3005 --env-file .env.practice --reload
```

```powershell
# Desde frontend
npm run dev
```

Si preparas una copia nueva del repositorio, guarda primero tu configuración de frontend y copia `frontend/.env.practica` a `frontend/.env`. Ingresa con las credenciales de `database/.env.practice-access`. El respaldo local `frontend/.env.institucional` conserva la configuración anterior para cuando toque trabajar con el historial institucional. Los reportes PDF de práctica llevan su marca de entorno dentro del documento.

## Despliegue en Vercel

En Vercel, el frontend SSR usa `frontend/` como **Root Directory**, con la compilación `pnpm run build`. Configura `API_SERVER_URL` con la URL HTTPS de FastAPI terminada en `/api` y `SESSION_SECRET` con una clave propia del entorno. El navegador usa `/api/servicio` para las operaciones directas y la sesión comparte el origen del frontend. [React Router en Vercel](https://vercel.com/docs/frameworks/frontend/react-router)

FastAPI usa `backend_fastapi/` como raíz de su servicio, con `app/main.py` como punto de entrada. Configura la conexión de Supabase mediante **Session pooler**, `POSTGRES_TLS_VERIFY=true` y `POSTGRES_TLS_CA_PEM` con el texto del certificado CA. Configura también Storage, los secretos de sesión y el origen autorizado desde las variables del servicio. Los SQL y respaldos quedan fuera de las raíces de ambos servicios. Ejecuta las migraciones por separado desde una máquina con acceso al repositorio. El entrenamiento sigue siendo una tarea de consola. [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi) · [Conexiones de PostgreSQL en Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)

Para funciones con el límite estándar de 4,5 MB por solicitud, configura `VITE_MAX_UPLOAD_MB=4` en el frontend. Así los formularios declaran un límite que deja espacio para la envoltura multipart. Si el sitio requiere conservar la carga de PDF de hasta 10 MB, el entorno publicado necesita un límite de plataforma suficiente o un flujo de carga directa. Comprueba también el tamaño del paquete de FastAPI con sus dependencias de machine learning. [Límites de Vercel Functions](https://vercel.com/docs/functions/limitations)

En las URLs definitivas, verifica el inicio de sesión, la descarga de PDF, las imágenes y el acceso a Supabase desde ambos servicios.
