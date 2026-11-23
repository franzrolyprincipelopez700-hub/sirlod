# Aprendizaje automático en SIRLOD

## Recorrido para la demostración

1. Inicia sesión como administrador. En **Analítica**, cada módulo abre en **Operación** y muestra el origen de los registros. **Evaluación del modelo** permite inspeccionar métricas, versiones y ejecutar los tres modelos experimentales. La instalación de demostración usa su propio esquema de Supabase. [Configuración del entorno](../../database/README.md).
2. Abre **Demanda de losas** para comparar el uso histórico, filtrar el mapa de disponibilidad por fecha o losa y consultar alternativas. Una cuenta de estudiante puede buscar alternativas en **Horarios de Atención**. La reserva vuelve a validar el turno al procesarse. [Demanda de losas](http://localhost:5174/dashboard/demanda).
3. Abre **Alertas de actividad** y expande un incidente pendiente. Allí puedes consultar evidencia, documentar una decisión y revisar el expediente. Una alerta estadística se puede descartar o derivar a un incidente con evidencia independiente. La prueba `test_attendance_restriction_expiry_and_unjust_penalty_correction` cubre el vencimiento y la corrección de una sanción. [Alertas de actividad](http://localhost:5174/dashboard/anomalias).
4. Abre **Asistencia y riesgo** para ver los resultados verificados, filtrar turnos y registrar la asistencia de un turno concluido. En **Evaluación del modelo**, ejecuta un caso experimental y muestra el resultado para compararlo con el pronóstico. Seguridad puede verificar asistencia desde su propio panel. [Asistencia y riesgo](http://localhost:5174/dashboard/asistencia).

Los tres modelos de demostración ya están guardados en Supabase. La última consulta confirmó Random Forest para demanda con 4 704 ejemplos, Isolation Forest para anomalías con 960 y Random Forest para inasistencia con 4 704. Los tamaños corresponden a los conjuntos completos de datos sintéticos. Las tres ejecuciones con datos reales tienen estado **Insuficiente** y ninguna está activa. El entrenamiento se puede repetir por consola con los comandos de esta guía.

## Arquitectura y diagnóstico

React Router SSR usa las sesiones y el cliente HTTP existentes. FastAPI centraliza la autorización, las transacciones y la disponibilidad. La instalación migrada consulta el esquema `padron_unheval` en el mismo PostgreSQL de Supabase para aplicar el cupo por escuela y año académico. El adaptador HTTP de Express/MySQL sigue disponible para otras instalaciones. Los modelos consultan PostgreSQL por medio de SQLAlchemy asíncrono. Gemini, DeepSeek, reportes y almacenamiento siguen sus circuitos de aplicación.

Antes de esta ampliación, `permisos` y `detalle_permisos` ya representaban reservas normales, permisos especiales y los estados pendiente, aceptado, rechazado y cancelado. `dias_bloqueados` y `configuracion_global` definían disponibilidad y cupos. El módulo de Seguridad consultaba permisos aceptados y el esquema carecía de resultado verificable de asistencia y expediente disciplinario. El plan académico del proyecto describe los requisitos de explicabilidad y revisión humana. El repositorio no aporta un instrumento que autorice sanciones administrativas.

El entorno de verificación usó Python 3.12.7, FastAPI 0.142.2, SQLAlchemy 2.1.3, asyncpg 0.32.0, PostgreSQL 18.4, Node 24.17.0, React 19.2.8 y React Router 8.0.0. El proyecto declara Python 3.11 o posterior. El plugin legado de SQLAlchemy para mypy se retiró porque SQLAlchemy 2.1 incorpora tipos nativos y ya no contiene el plugin.

## Instalación y migración

Desde `backend_fastapi`, con la conexión de desarrollo correctamente configurada:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m scripts.migrate_learning
.\.venv\Scripts\python.exe -m scripts.check_database
```

Como alternativa, ejecuta `database/postgres/migrations/20261122_learning.sql` con `psql -v ON_ERROR_STOP=1` después de las migraciones anteriores. La migración es aditiva, transaccional e idempotente. Requiere poder crear tablas e índices en el esquema utilizado por SIRLOD. El verificador comprueba las columnas de los modelos ORM, incluidas las nueve tablas nuevas de resultados, medidas, incidentes, auditoría y aprendizaje.

El proyecto añade scikit-learn 1.7.2 para construir, comparar y calibrar estimadores, skops 0.16.0 para serializarlos y tzdata para disponer de `America/Lima` en Windows. Los artefactos se guardan en `ml_modelos` con huella SHA-256, firma HMAC, versiones de librerías y esquema de variables. La inferencia verifica integridad, firma de metadatos, compatibilidad, tamaño y tipos autorizados. FastAPI y el proceso de entrenamiento deben compartir `ML_ARTIFACT_SECRET`. Si se omite, el sistema usa `JWT_SECRET` con un dominio de firma propio. Al rotar la clave de firma, se requiere reentrenar y habilitar versiones nuevas. Las versiones reales solo se activan explícitamente si superan la evaluación. Las versiones sintéticas se almacenan bajo modo `demo` y PostgreSQL impide activarlas.

## Entrenamiento, evaluación y activación

Ejecuta los comandos desde `backend_fastapi` con el entorno virtual activado. El entrenamiento ocurre en un proceso de consola y se excluyen ejecuciones concurrentes de la misma modalidad y módulo.

```powershell
python -m scripts.learning train --mode demo
python -m scripts.learning train --mode real
python -m scripts.learning train --mode real --module inasistencia
python -m scripts.learning activate UUID_REAL_EVALUADO
python -m scripts.learning scan-anomalies
```

Se puede seleccionar `demanda`, `anomalias`, `inasistencia` o `all`. Cada ejecución registra una nueva versión, su resultado, el intervalo y la cobertura de las particiones. Una ejecución insuficiente o rechazada no reemplaza la versión real activa. La activación por UUID también está disponible en el panel de administrador. Para volver a un modelo anterior, activa su versión real evaluada y compatible.

El modo de demostración genera ejemplos reproducibles en memoria. El panel permite ejecutar inferencia en esos ejemplos y ver sus objetivos y puntuaciones. Los ejemplos no se insertan en permisos, asistencias, intentos ni expedientes. El modo real consulta PostgreSQL y separa entrenamiento, selección de modelos y prueba por fecha civil de Lima. Cuando una etiqueta todavía no estaba disponible al empezar la partición siguiente, se descarta esa fila de la partición anterior. Los parámetros de evaluación son criterios técnicos de este proyecto, sujetos a revisión con datos institucionales.

| Módulo | Datos y evaluación | Comportamiento operativo |
| --- | --- | --- |
| RF-04 | Reconstruye turnos de una hora en hasta 365 días, desde la primera actividad observada por losa. El objetivo es ocupación por un permiso aceptado al consultar el histórico. Usa losa, disciplina, mes, día de semana y hora. Compara Random Forest e HistGradientBoosting por Brier en validación. La prueba debe mejorar la frecuencia global de entrenamiento y alcanzar ROC-AUC ≥ 0.60. | Consulta apertura, bloqueos, vigencia de la cuenta, estado de losa y disciplina, permisos pendientes y aceptados, y el cupo del padrón para reservas normales. Ordena alternativas libres. Con pocas muestras muestra disponibilidad, o la frecuencia observada cuando hay al menos cuatro turnos históricos comparables. La creación vuelve a validar la selección y serializa las escrituras por losa. |
| RF-05 | Agrupa actividad por cuenta y semana cerrada. Usa solicitudes, cancelaciones, intentos registrados, concentración en una franja y variación frente a cuatro semanas anteriores. Compara Isolation Forest y Local Outlier Factor con perturbaciones controladas y estabilidad temporal. Un valor mayor representa mayor rareza. El umbral se estima con el percentil 97 de validación. | El análisis por consola o panel abarca hasta cuatro semanas cerradas y abre una alerta auditable por cuenta y semana. La evidencia incluye variables y umbral. El administrador puede descartar la alerta o derivarla a un incidente con una fuente verificable independiente. |
| RF-06 | Usa exclusivamente asistencia verificada en turnos aceptados y finalizados. Emplea características conocidas al confirmar el permiso, como fecha, losa, disciplina, tipo, duración y antelación. Compara regresión logística y Random Forest, con calibración sigmoide en un periodo separado. Evalúa Brier, ROC-AUC, F1, precisión, recall, matriz de confusión y calibración en prueba. | La validación selecciona el umbral alto por F1. La mitad de ese umbral separa riesgo bajo y medio como criterio operativo de seguimiento. El administrador puede calcular riesgo individual y generar una lista de seguimiento para los próximos siete días. Seguridad registra la asistencia real. Una estimación no modifica permisos ni abre expedientes. |

El análisis de errores supervisados incluye Brier por hora. Los metadatos reflejan la cobertura mínima por periodo, ambas clases en los modelos supervisados y diversidad de cuentas para inasistencia y anomalías. No se usan nombres, documentos de identidad, IP, escuela, año académico ni identificadores de cuenta como variables predictivas. La escuela y el año se consultan para validar el cupo existente, independiente del modelo.

## Uso desde la aplicación

1. **Estudiante.** En **Horarios de Atención**, elige modalidad y fecha y pulsa **Buscar alternativas**. Selecciona una sugerencia para usar la confirmación de reserva existente. Los permisos especiales siguen requiriendo PDF y aprobación.
2. **Administrador.** En **Analítica**, abre el módulo correspondiente y consulta **Modelo y evaluación**. Usa **Práctica** para los casos de entrenamiento y **Operación** para la actividad registrada. Los expedientes permiten revisar medidas y descargos.
3. **Seguridad.** En **Asistencia**, filtra por fecha y código. Registra el resultado de un turno terminado con la evidencia de garita disponible. `pendiente` representa un turno sin concluir, `sin_verificar` un turno finalizado sin evidencia concluyente y `cancelado` un permiso cancelado. `asistio` e `inasistencia` requieren verificación. Las correcciones agregan un registro con autor y fecha. Si el resultado está vinculado a un incidente pendiente o confirmado, resuelve el incidente antes de corregirlo.
4. **Administrador.** En **Asistencia y riesgo**, consulta una reserva futura o evalúa el horizonte de siete días. Una inasistencia comprobada permite abrir un expediente con el registro de asistencia asociado. Otros hechos requieren referencia del acta o registro y evidencia verificable.
5. **Estudiante.** En **Mi situación**, consulta fechas, motivos y estado de medidas y presenta descargos propios. El acceso a la cuenta y al expediente propio sigue disponible durante una restricción.

## Política, revisión y auditoría

El sistema se instala sin reglas aprobadas. En **Normativa configurable** un administrador registra borradores con fundamento, criterio verificable, gravedad, número mínimo de infracciones válidas previas y máximo de horas para medidas restrictivas. La habilitación requiere consignar el instrumento institucional aprobado. El software conserva esa referencia y el administrador que la registró. La institución debe verificar la autenticidad y el alcance del instrumento antes de habilitarlo.

Las medidas preventivas de esta implementación se limitan a inasistencias verificadas con incidente pendiente y regla aprobada. Las advertencias y suspensiones disciplinarias requieren confirmación humana del hecho. Se aplica el nivel más alto autorizado por el número de infracciones válidas anteriores que corresponda al caso. Las medidas restrictivas tienen inicio y fin. Al vencer dejan de bloquear nuevas reservas. Un administrador puede levantarlas anticipadamente, resolver descargos o anular una decisión errónea, dejando motivo y trazabilidad. Las medidas graves requieren clasificación explícita y una regla aprobada para esa gravedad.

En particular, anular una sanción disciplinaria corrige la infracción asociada, excluye ambas del cómputo posterior y conserva el expediente corregido en la auditoría autorizada. Las medidas levantadas o cumplidas permanecen en el histórico válido cuando la infracción sigue confirmada. Los descargos están vinculados a la medida específica y su resolución queda registrada.

## Pruebas y alcance de los datos

```powershell
# Ejecutar en una base desechable PostgreSQL con permiso para crear y borrar esquemas de prueba.
$env:SIRLOD_TEST_DATABASE_URL = "postgresql+asyncpg://USUARIO:CLAVE@127.0.0.1:5432/BASE_DE_PRUEBA"
python -m pytest
python -m ruff check app tests scripts
python -m mypy app
python -m compileall -q app scripts
```

Las pruebas de integración crean esquemas aislados, aplican las migraciones y después eliminan exclusivamente esos esquemas. Ejercitan extracción y entrenamiento desde PostgreSQL, autorización, carreras entre reservas, asistencia, puntuación, vencimiento, descargos y anulación. Para el frontend, ejecuta `npm run typecheck`, `npm run build` y `node scripts/test-reservation-response.mjs` desde `frontend`.

RF-04 reconstruye el historial con las ventanas actuales y los bloqueos registrados. Las etapas antiguas sin calendario de mantenimiento ni aperturas históricas limitan la comparabilidad. RF-05 observa los intentos instrumentados desde esta versión y las cancelaciones conservadas en el estado del permiso. El padrón académico no aporta evidencia verificable de coordinación entre cuentas. RF-06 necesita acumular suficientes resultados comprobados. La conexión institucional y la validación con casos legítimos son necesarias para evaluar si los modelos se pueden activar en la institución. Las métricas de demostración solo describen el generador sintético y sus particiones.

## Archivos de la integración

- `database/postgres/migrations/20261122_learning.sql` crea las tablas, restricciones e índices. `backend_fastapi/scripts/migrate_learning.py` aplica la migración y `scripts/check_database.py` comprueba el esquema.
- `backend_fastapi/app/modules/learning/` contiene la extracción, variables, evaluación, registro de modelos, servicios de inferencia, asistencia, expedientes y API. `backend_fastapi/scripts/learning.py` ejecuta el entrenamiento y el análisis por lotes.
- `backend_fastapi/app/modules/permisos/{router,schemas,service}.py` integra la verificación de acceso e instrumenta intentos en la ruta existente. `app/core/clock.py` fija la hora del campus y `app/core/config.py` incorpora la clave de firma opcional.
- `frontend/app/features/ia/` contiene las vistas y acciones de Inteligencia artificial, Asistencia, Mi situación y las sugerencias de horarios. `frontend/app/features/horarios/_public.horario.tsx` conecta las sugerencias con la confirmación de reserva. `frontend/app/routes.ts` y los componentes de navegación enlazan las nuevas vistas.
- `backend_fastapi/tests/test_learning.py` prueba modelos, cortes temporales y serialización. `tests/test_learning_postgres.py` verifica los flujos transaccionales con PostgreSQL. La regresión de OpenAPI y `frontend/scripts/test-reservation-response.mjs` comprueban los contratos de rutas existentes.

Referencias técnicas. [Persistencia de modelos de scikit-learn](https://scikit-learn.org/1.7/model_persistence.html), [calibración de probabilidades](https://scikit-learn.org/1.7/modules/calibration.html) y [serialización segura con skops](https://skops.readthedocs.io/en/stable/persistence.html).

