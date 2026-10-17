# Agente de Inventario con IA

Asistente conversacional para una tienda familiar de suministros para cafeterías. Carla, la dueña, le habla en lenguaje natural ("acaban de llegar 30 unidades de leche de avena", "¿qué se está agotando?") y el agente consulta y actualiza el stock.

El sistema tiene dos partes:

1. **API REST** (`api/app.py`) con FastAPI. Gestiona el inventario y lo guarda en `products.csv`.
2. **Agente** (`agent.py`) en Python puro, **sin frameworks de agentes**. Usa un LLM de Groq con tool calling y la API como conjunto de herramientas. Cada evento se registra en `conversation_log.csv`.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Una clave de API de [Groq](https://console.groq.com)

## Instalación

```bash
uv sync
```

Crea un fichero `.env` en la raíz (está en `.gitignore`, nunca se sube):

```
GROQ_API_KEY=tu_clave_aqui
GROQ_MODEL=openai/gpt-oss-120b
```

`GROQ_MODEL` es opcional. Si el modelo deja de estar disponible en Groq, basta con cambiarlo aquí.

## Cómo arrancar el sistema

Necesitas **dos terminales** abiertos en la raíz del proyecto. La API debe estar en marcha antes que el agente.

```bash
# Terminal 1: API
uv run uvicorn api.app:app --reload

# Terminal 2: agente
uv run python agent.py
```

- **Detener:** escribe `salir` en el agente (o pulsa `Ctrl + C`) y después `Ctrl + C` en la API.
- **Relanzar el agente:** vuelve a ejecutar `uv run python agent.py`. No hace falta reiniciar la API. El log conserva todas las sesiones anteriores.
- **Documentación interactiva de la API:** http://127.0.0.1:8000/docs

## API

| Método | Endpoint                         | Descripción                                            | Errores                                                                |
| ------ | -------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------- |
| GET    | `/inventory`                     | Lista todos los productos                              | —                                                                      |
| POST   | `/inventory`                     | Crea un producto (`name`, `quantity`, `unit`)          | `409` si el nombre ya existe, `422` si los datos no son válidos        |
| PATCH  | `/inventory/{product_id}`        | Suma o resta stock con `delta` (+ entradas, − salidas) | `404` si no existe, `400` si `delta` es 0 o el stock quedaría negativo |
| GET    | `/inventory/alerts?threshold=10` | Productos por debajo del umbral (por defecto 10)       | `422` si el umbral es negativo                                         |

Si `products.csv` no existe, se crea con un catálogo inicial de ejemplo.

## Agente

### Tools

| Tool                   | Endpoint                        |
| ---------------------- | ------------------------------- |
| `get_inventory`        | `GET /inventory`                |
| `add_product`          | `POST /inventory`               |
| `update_stock`         | `PATCH /inventory/{product_id}` |
| `get_low_stock_alerts` | `GET /inventory/alerts`         |

### Bucle

Implementado a mano en `run_agent_turn()`:

```
Observar   → leer el mensaje de Carla
Pensar     → enviar el historial completo + las tools al LLM
Actuar     → ejecutar las tools que pida el LLM (llamando a la API)
Actualizar → inyectar cada resultado en el historial como mensaje "tool"
Repetir    → hasta que el LLM responda sin pedir tools
```

- El historial completo se mantiene en memoria durante la sesión, así el agente entiende referencias como "¿y cuánto me queda de eso?".
- Los errores de la API (404, 400, API apagada) se devuelven al LLM como resultado, que se los explica a Carla, en vez de romper el programa.
- Hay un límite de 10 iteraciones por turno como freno de seguridad.
- Si un producto no existe, el agente pregunta antes de darlo de alta.

## Registro de conversación

`conversation_log.csv` es **append-only**: cada sesión añade filas y nunca sobrescribe.

| Campo       | Contenido                                            |
| ----------- | ---------------------------------------------------- |
| `actor`     | `user`, `agent` o `tool`                             |
| `message`   | Texto del mensaje, argumentos de la tool o resultado |
| `tool_call` | Nombre de la tool (vacío si no aplica)               |
| `timestamp` | Fecha y hora ISO 8601 con zona horaria               |

## Ejemplo

```
Carla > acaban de llegar 30 unidades de leche de avena
Agente > Listo, la leche de avena ahora tiene 68 unidades en stock.

Carla > ¿qué productos están por agotarse?
Agente > Solo la canela molida: quedan 3 kg.

Carla > vendimos 12 bolsas de arábica hoy
Agente > Registrada la venta: quedan 13 bolsas de café arábica en grano.

Carla > ¿y cuánto me queda de eso?
Agente > Te quedan 13 bolsas de café arábica en grano.
```

## Estructura

```
├── api/
│   └── app.py              # API FastAPI + capa de datos CSV
├── agent.py                # Bucle del agente, tools, dispatcher, log y CLI
├── products.csv            # Inventario (se crea automáticamente)
├── conversation_log.csv    # Registro de conversación (append-only)
├── pyproject.toml
└── .env                    # Clave de Groq (no se sube)
```
