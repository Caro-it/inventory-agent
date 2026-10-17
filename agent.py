import csv
import json
import os
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


# ---------- System prompt ----------
SYSTEM_PROMPT = """Eres el asistente de inventario de una tienda familiar de suministros para cafeterías.
Hablas con Carla, la dueña, que te cuenta entregas, ventas y te hace preguntas sobre el stock.

Reglas:
- Usa SIEMPRE las herramientas para consultar o modificar datos. Nunca inventes cantidades, productos ni ids.
- Para cambiar el stock necesitas el id del producto. Si no lo conoces, llama primero a get_inventory y búscalo por nombre.
- Entregas o llegadas de mercancía = delta POSITIVO. Ventas, consumos o salidas = delta NEGATIVO.
- Si Carla menciona un producto que no existe en el inventario, pregúntale si quiere darlo de alta y en qué unidad, antes de crearlo.
- Si una herramienta devuelve un error, explícaselo a Carla con palabras sencillas.
- Responde en español, de forma breve y natural, incluyendo siempre cantidades y unidades."""

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


if __name__ == "__main__":
    # Prueba temporal: comprobar que el modelo elige una tool (se quita en el paso 9)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "¿Qué productos están por agotarse?"},
        ],
        tools=TOOLS,
    )
    msg = response.choices[0].message
    print("content:", msg.content)
    for tc in msg.tool_calls or []:
        print("tool:", tc.function.name, "| args:", tc.function.arguments)