import csv
import json
import os
import httpx
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------- Configuración ----------
load_dotenv()

API_URL = os.getenv("INVENTORY_API_URL", "http://127.0.0.1:8000")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",  # endpoint de Groq compatible con OpenAI
)

# ---------- Registro de conversación ----------
LOG_FILE = Path(__file__).resolve().parent / "conversation_log.csv"
LOG_FIELDS = ["actor", "message", "tool_call", "timestamp"]


def log_event(actor: str, message: str, tool_call: str | None = None) -> None:
    """Añade un evento al log. Crea la cabecera si el fichero no existe."""
    file_exists = LOG_FILE.exists()  # antes de abrir: el modo "a" crea el fichero

    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "actor": actor,
                "message": message,
                "tool_call": tool_call or "",
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )


SYSTEM_PROMPT = """Eres el asistente de inventario de una tienda familiar de suministros para cafeterías.
Hablas con Carla, la dueña, que te cuenta entregas, ventas y te hace preguntas sobre el stock.

Reglas:
- Usa SIEMPRE las herramientas para consultar o modificar datos. Nunca inventes cantidades, productos ni ids.
- Para cambiar el stock necesitas el id del producto. Si no lo conoces, llama primero a get_inventory y búscalo por nombre.
- Entregas o llegadas de mercancía = delta POSITIVO. Ventas, consumos o salidas = delta NEGATIVO.
- Si Carla menciona un producto que no existe en el inventario, pregúntale si quiere darlo de alta y en qué unidad, antes de crearlo.
- Si una herramienta devuelve un error, explícaselo a Carla con palabras sencillas.
- Responde en español, de forma breve y natural, incluyendo siempre cantidades y unidades.
- Responde en texto plano, sin formato Markdown (sin asteriscos ni almohadillas)."""

# ---------- Definición de tools ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": "Devuelve todos los productos del inventario con su id, nombre, cantidad y unidad. "
                           "Úsala para consultar el stock o para encontrar el id de un producto por su nombre.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Da de alta un producto NUEVO en el inventario. "
                           "No la uses para productos que ya existen: para eso está update_stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del producto, p. ej. 'Canela molida'"},
                    "quantity": {"type": "number", "description": "Cantidad inicial, mayor o igual que 0"},
                    "unit": {"type": "string", "description": "Unidad de medida: unidades, kg, litros, bolsas..."},
                },
                "required": ["name", "quantity", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": "Suma o resta stock a un producto existente. "
                           "Delta positivo para entregas/entradas, negativo para ventas/salidas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Id del producto (obtenlo con get_inventory)"},
                    "delta": {"type": "number", "description": "Cambio de cantidad: +30 si llegan 30, -12 si se venden 12"},
                },
                "required": ["product_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Devuelve los productos con stock por debajo de un umbral (por defecto 10). "
                           "Úsala cuando Carla pregunte qué se está agotando o qué hay que reponer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "description": "Umbral opcional. Si no se indica, se usa 10."},
                },
                "required": [],
            },
        },
    },
]
# ---------- Dispatcher: ejecuta la tool llamando a la API ----------
def execute_tool(name: str, args: dict) -> str:
    """Llama al endpoint correspondiente y devuelve el resultado como string JSON."""
    try:
        if name == "get_inventory":
            response = httpx.get(f"{API_URL}/inventory", timeout=10)

        elif name == "add_product":
            body = {"name": args["name"], "quantity": args["quantity"], "unit": args["unit"]}
            response = httpx.post(f"{API_URL}/inventory", json=body, timeout=10)

        elif name == "update_stock":
            response = httpx.patch(
                f"{API_URL}/inventory/{args['product_id']}",
                json={"delta": args["delta"]},
                timeout=10,
            )

        elif name == "get_low_stock_alerts":
            params = {}
            if args.get("threshold") is not None:
                params["threshold"] = args["threshold"]
            response = httpx.get(f"{API_URL}/inventory/alerts", params=params, timeout=10)

        else:
            return json.dumps({"error": f"Tool desconocida: {name}"}, ensure_ascii=False)

    except httpx.ConnectError:
        return json.dumps(
            {"error": "No se puede conectar con la API de inventario. ¿Está arrancada?"},
            ensure_ascii=False,
        )
    except KeyError as missing:
        return json.dumps({"error": f"Falta el parámetro {missing}"}, ensure_ascii=False)

    # Respuesta de la API: éxito o error HTTP
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.is_error:
        detail = data.get("detail", data) if isinstance(data, dict) else data
        return json.dumps({"error": detail, "status_code": response.status_code}, ensure_ascii=False)

    return json.dumps(data, ensure_ascii=False)

# ---------- Bucle del agente ----------
MAX_ITERATIONS = 10  # freno de seguridad por si el modelo encadena tools sin parar


def run_agent_turn(messages: list[dict]) -> str:
    """Ejecuta el bucle Pensar → Actuar → Actualizar → Repetir para un mensaje de Carla."""
    for _ in range(MAX_ITERATIONS):
        # PENSAR: enviar todo el historial + las tools al LLM
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
        msg = response.choices[0].message

        # FIN: respuesta final sin tools pendientes
        if not msg.tool_calls:
            final_answer = msg.content or ""
            messages.append({"role": "assistant", "content": final_answer})
            log_event("agent", final_answer)
            return final_answer

        # Guardar la decisión del LLM ANTES de los resultados (regla 1 de la traza)
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # ACTUAR + ACTUALIZAR: ejecutar cada tool pedida e inyectar su resultado
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            log_event("agent", tc.function.arguments or "{}", tool_name)

            try:
                args = json.loads(tc.function.arguments or "{}")
                result = execute_tool(tool_name, args)
            except json.JSONDecodeError:
                result = json.dumps({"error": "Argumentos no válidos (JSON mal formado)"}, ensure_ascii=False)

            log_event("tool", result, tool_name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,  # regla 2 de la traza
                    "content": result,
                }
            )
        # REPETIR: vuelve al principio del for con el historial actualizado

    # Regla 3: límite alcanzado
    fallback = "Lo siento, no he podido completar la petición. ¿Puedes reformularla?"
    messages.append({"role": "assistant", "content": fallback})
    log_event("agent", fallback)
    return fallback


# ---------- CLI ----------
def main() -> None:
    print("Asistente de inventario. Escribe 'salir' para terminar.\n")
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        # OBSERVAR: leer el input de Carla
        try:
            user_input = input("Carla > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nHasta luego.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"salir", "exit", "quit"}:
            print("Hasta luego.")
            break

        checkpoint = len(messages)  # para deshacer el turno si algo falla a medias
        log_event("user", user_input)
        messages.append({"role": "user", "content": user_input})

        try:
            answer = run_agent_turn(messages)
        except Exception as error:  # fallo de red o del LLM
            del messages[checkpoint:]  # evita dejar un historial inconsistente
            answer = f"Ha habido un problema al contactar con el modelo: {error}"
            log_event("agent", answer)

        print(f"Agente > {answer}\n")


if __name__ == "__main__":
    main()
    