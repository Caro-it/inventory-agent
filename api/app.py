import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

# ---------- Configuración ----------
BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
PRODUCTS_FILE = BASE_DIR / "products.csv"
FIELDS = ["id", "name", "quantity", "unit"]
DEFAULT_ALERT_THRESHOLD = 10

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


# ---------- Modelos ----------
class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Nombre del producto")
    quantity: float = Field(..., ge=0, description="Cantidad inicial (>= 0)")
    unit: str = Field(..., min_length=1, description="Unidad de medida: unidades, kg, litros, bolsas...")


class Product(ProductCreate):
    id: int


class StockUpdate(BaseModel):
    delta: float = Field(
        ...,
        description="Cambio de stock: positivo para entradas, negativo para salidas/ventas",
    )


class AlertsResponse(BaseModel):
    threshold: float
    count: int
    products: list[Product]


# ---------- API ----------
app = FastAPI(
    title="Inventario de Carla",
    description="API de inventario para la tienda de suministros de cafetería",
)


@app.get("/inventory", response_model=list[Product])
def get_inventory():
    """Devuelve la lista completa de productos."""
    return load_products()


@app.post("/inventory", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate):
    """Añade un producto nuevo. Rechaza nombres duplicados."""
    products = load_products()

    if any(p["name"].lower() == payload.name.lower() for p in products):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un producto llamado '{payload.name}'. Usa PATCH para cambiar su stock.",
        )

    new_product = {"id": next_id(products), **payload.model_dump()}
    products.append(new_product)
    save_products(products)
    return new_product


@app.patch("/inventory/{product_id}", response_model=Product)
def update_stock(product_id: int, payload: StockUpdate):
    """Suma (entrada) o resta (venta/salida) stock a un producto existente."""
    if payload.delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El delta no puede ser 0.",
        )

    products = load_products()
    product = next((p for p in products if p["id"] == product_id), None)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún producto con id {product_id}.",
        )

    new_quantity = round(product["quantity"] + payload.delta, 3)
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Stock insuficiente de '{product['name']}': hay {product['quantity']} "
                f"{product['unit']} y se intentan restar {abs(payload.delta)}."
            ),
        )

    product["quantity"] = new_quantity
    save_products(products)
    return product


@app.get("/inventory/alerts", response_model=AlertsResponse)
def get_alerts(
    threshold: float = Query(
        DEFAULT_ALERT_THRESHOLD,
        ge=0,
        description="Umbral de stock bajo (por defecto 10)",
    ),
):
    """Devuelve los productos cuya cantidad está por debajo del umbral."""
    low_stock = [p for p in load_products() if p["quantity"] < threshold]
    return {"threshold": threshold, "count": len(low_stock), "products": low_stock}