import csv
from datetime import datetime
from pathlib import Path

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


if __name__ == "__main__":
    # Prueba temporal: la quitaremos en el paso 9
    log_event("user", "acaban de llegar 30 leches de avena")
    log_event("tool", '{"id": 2, "quantity": 38}', "update_stock")
    log_event("agent", "Hecho, ahora hay 38 unidades de leche de avena.")