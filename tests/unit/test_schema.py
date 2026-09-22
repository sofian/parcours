from parcours.core.schema import load_category_schema, load_all_schemas


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_fields_dedup_and_require_one_of(tmp_path):
    schema_file = _write(tmp_path / "widgets.yaml", """
name: widgets
handler: generic
options:
  some_option: value
fields:
  - {name: id, generated: true}
  - {name: title_en}
  - {name: title_fr}
  - {name: status, required: true, vocab: widget_status}
  - {name: start_date, type: date, precision: month, required: true}
require_one_of:
  - [title_en, title_fr]
dedup:
  - when: [{exact: id}]
    as: duplicate
""")
    schema = load_category_schema(schema_file)

    assert schema.name == "widgets"
    assert schema.handler == "generic"
    assert schema.options == {"some_option": "value"}
    assert schema.field_names() == ["id", "title_en", "title_fr", "status", "start_date"]
    assert schema.require_one_of == [["title_en", "title_fr"]]

    status_field = schema.get_field("status")
    assert status_field.required is True
    assert status_field.vocab == "widget_status"

    date_field = schema.get_field("start_date")
    assert date_field.type == "date"
    assert date_field.precision == "month"

    assert schema.get_field("nonexistent") is None

    assert len(schema.dedup) == 1
    assert schema.dedup[0].conditions == [{"exact": "id"}]
    assert schema.dedup[0].outcome == "duplicate"


def test_handler_defaults_to_generic(tmp_path):
    schema_file = _write(tmp_path / "minimal.yaml", """
name: minimal
fields:
  - {name: id, generated: true}
""")
    schema = load_category_schema(schema_file)
    assert schema.handler == "generic"
    assert schema.options == {}
    assert schema.dedup == []
    assert schema.require_one_of == []


def test_load_all_schemas_keys_by_category_name(tmp_path):
    categories_dir = tmp_path / "categories"
    categories_dir.mkdir()
    _write(categories_dir / "widgets.yaml", "name: widgets\nfields: [{name: id, generated: true}]\n")
    _write(categories_dir / "gadgets.yaml", "name: gadgets\nfields: [{name: id, generated: true}]\n")

    schemas = load_all_schemas(categories_dir)

    assert set(schemas.keys()) == {"widgets", "gadgets"}
    assert schemas["widgets"].name == "widgets"
