"""
Tests for the DBDiagram.io (DBML) subset importer and its API endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dbml import parse_dbml, DbmlParseError
from app.models.schema import DbmlImportRequest


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


DBML_DOC = """\
Project 'My Shop' {
  database_type: 'PostgreSQL'
}

Table users {
  id int [pk, increment]
  full_name varchar
  email varchar [unique, not null]
  phone varchar [null]
  signup_date date
  is_active boolean [not null]
  balance decimal(10,2)
}

Table orders {
  id int [pk]
  customer_id int [not null]
  status varchar
  created_at timestamp [not null]
}

Ref: orders.customer_id > users.id

Table order_items {
  id int [pk]
  order_id int
  product_id int
}

Ref: order_items.order_id > orders.id

Table products {
  id int [pk]
  title varchar
}

Ref: order_items.product_id > products.id

enum order_status {
  pending
  shipped
  delivered
}
"""


def _minimal_table_doc(pk: str) -> str:
    return f"""\
Table a {{
  id {pk} [pk]
  name varchar
}}
Table b {{
  id {pk} [pk]
  a_id int [ref: > a.id]
}}
"""


def test_parse_full_document() -> None:
    result = parse_dbml(DBML_DOC, fallback_name="Fallback")

    assert result.name == "My Shop"
    names = [e["name"] for e in result.entities]
    assert names == ["users", "orders", "order_items", "products"]

    users = result.entities[0]
    by_name = {a["name"]: a for a in users["attributes"]}
    assert by_name["id"]["type"] == "autoincrement"
    assert by_name["id"]["is_primary_key"] is True
    assert by_name["email"]["type"] == "email"
    assert by_name["email"]["nullable"] is False
    assert by_name["phone"]["nullable"] is True
    assert by_name["signup_date"]["type"] == "date_time"
    assert by_name["is_active"]["type"] == "boolean"
    assert by_name["balance"]["type"] == "numeric_range"
    assert by_name["balance"]["params"]["is_float"] is True

    orders = result.entities[1]
    cust = next(a for a in orders["attributes"] if a["name"] == "customer_id")
    assert cust["type"] == "foreign_key"
    assert cust["fk_target"] == "users.id"

    items = result.entities[2]
    assert {a["fk_target"] for a in items["attributes"] if a["type"] == "foreign_key"} == {
        "orders.id", "products.id"
    }


def test_enum_mapping() -> None:
    doc = """\
enum status { pending, shipped, delivered }
Table shipments {
  id int [pk]
  status status
}
"""
    result = parse_dbml(doc)
    attr = next(a for a in result.entities[0]["attributes"] if a["name"] == "status")
    assert attr["type"] == "categorical"
    assert attr["params"]["choices"] == ["pending", "shipped", "delivered"]


def test_aliases_and_backrefs() -> None:
    doc = """\
Table users as u {
  id int [pk]
}
Table orders {
  id int [pk]
  buyer int [ref: < u.id]
}
"""
    result = parse_dbml(doc)
    orders = result.entities[1]
    buyer = next(a for a in orders["attributes"] if a["name"] == "buyer")
    assert buyer["type"] == "foreign_key"
    assert buyer["fk_target"] == "users.id"


def test_composite_pk_rejected() -> None:
    with pytest.raises(DbmlParseError) as exc:
        parse_dbml("Table t {\n a int [pk]\n b int [pk]\n}")
    assert any("Composite primary key" in d.message for d in exc.value.diagnostics)


def test_ref_to_missing_table_rejected() -> None:
    doc = "Table t {\n id int [pk]\n other int [ref: > ghost.id]\n}"
    with pytest.raises(DbmlParseError) as exc:
        parse_dbml(doc)
    assert any("unknown table" in d.message for d in exc.value.diagnostics)
    assert exc.value.diagnostics[0].line == 3


def test_unbalanced_braces_rejected() -> None:
    with pytest.raises(DbmlParseError):
        parse_dbml("Table t { id int [pk]")


def test_settings_style_project_name() -> None:
    doc = 'Project {\n name: \'widgets\'\n}\nTable t {\n id int [pk]\n}'
    result = parse_dbml(doc)
    assert result.name == "widgets"


def test_indexes_warn_but_import() -> None:
    doc = """\
Table t {
  id int [pk]
  indexes {
    (id) [type: hash]
  }
}
"""
    result = parse_dbml(doc)
    assert any("indexes" in w for w in result.warnings)
    assert len(result.entities[0]["attributes"]) == 1


def test_many_to_many_dash_ref_rejected() -> None:
    doc = "Table a {\n id int [pk]\n}\nTable b {\n id int [pk]\n a_id int [ref: -- a.id]\n}"
    with pytest.raises(DbmlParseError):
        parse_dbml(doc)


# ----------------------------------------------------------------------
# API endpoint
# ----------------------------------------------------------------------

def test_import_endpoint(client: TestClient) -> None:
    res = client.post(
        "/api/v1/schemas/import-dbml",
        json={"name": "shop", "source": DBML_DOC}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "My Shop"
    assert len(body["entities"]) == 4


def test_import_endpoint_invalid_dbml(client: TestClient) -> None:
    res = client.post(
        "/api/v1/schemas/import-dbml",
        json={"name": "shop", "source": "Table t { a int [pk] b int [pk] }"}
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "DBML_PARSE_ERROR"
    assert detail["diagnostics"][0]["line"] >= 1


def test_imported_entities_pass_generation_validation(client: TestClient) -> None:
    res = client.post(
        "/api/v1/schemas/import-dbml",
        json={"name": "shop", "source": _minimal_table_doc("int")}
    )
    assert res.status_code == 200
    entities = res.json()["entities"]

    from app.models.schema import GenerateRequest
    request = GenerateRequest(name="shop", entities=entities)  # type: ignore[arg-type]
    assert request.entities[1].attributes[-1].type == "foreign_key"
