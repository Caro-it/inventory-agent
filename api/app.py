import csv
from pathlib import Path

# ---------- Configuración ----------
BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
PRODUCTS_FILE = BASE_DIR / "products.csv"
FIELDS = ["id", "name", "quantity", "unit"]

SEED_PRODUCTS = [
    {"id": 1, "name": "Café arábica en grano", "quantity": 25, "unit": "bolsas"},
    {"id": 2, "name": "Leche de avena", "quantity": 8, "unit": "unidades"},
    {"id": 3, "name": "Leche entera", "quantity": 40, "unit": "litros"},
    {"id": 4, "name": "Azúcar", "quantity": 12.5, "unit": "kg"},
    {"id": 5, "name": "Vasos de cartón 8oz", "quantity": 300, "unit": "unidades"},
    {"id": 6, "name": "Tapas para vasos", "quantity": 5, "unit": "unidades"},
]


# ---------- Capa de datos (CSV) ----------
def ensure_products_file() -> None:
    """Crea products.csv con el catálogo inicial si no existe."""
    if not PRODUCTS_FILE.exists():
        save_products(SEED_PRODUCTS)


def load_products() -> list[dict]:
    """Lee todos los productos del CSV y convierte los tipos."""
    ensure_products_file()
    with PRODUCTS_FILE.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "quantity": float(row["quantity"]),
                "unit": row["unit"],
            }
            for row in reader
        ]


def save_products(products: list[dict]) -> None:
    """Sobrescribe el CSV con la lista completa de productos."""
    with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(products)


def next_id(products: list[dict]) -> int:
    """Devuelve el siguiente id libre."""
    return max((p["id"] for p in products), default=0) + 1