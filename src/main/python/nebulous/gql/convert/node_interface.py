from __future__ import annotations

import typing

from nebulous.text_utils.base64 import from_base64, to_base64, to_base64_sql
from sqlalchemy import text

from ..alias import Field, InterfaceType, NonNull, ScalarType

if typing.TYPE_CHECKING:
    pass


def to_global_id(table_name, values: typing.List[typing.Any]) -> str:
    """
    Takes a type name and an ID specific to that type name, and returns a
    "global ID" that is unique among all types.
    """
    return to_base64(table_name + "@" + ",".join([str(x) for x in values]))


def from_global_id(global_id: str) -> typing.Tuple[str, typing.List[str]]:
    """
    Takes the "global ID" created by toGlobalID, and returns the type name and ID
    used to create it.
    """
    try:
        unbased_global_id = from_base64(global_id)
        table_name, values = unbased_global_id.split("@", 1)
        # TODO(OR): Text fields in primary key might contain a comma
        values = values.split(",")
    except Exception:
        raise ValueError(f"Bad input: invalid NodeID {global_id}")
    return table_name, values


def to_global_id_sql(sqla_model) -> "sql_selector":
    table_name = sqla_model.table_name
    pkey_cols = list(sqla_model.primary_key.columns)

    selector = ", ||".join([f'"{col.name}"' for col in pkey_cols])

    str_to_encode = f"'{table_name}' || '@' || " + selector

    return to_base64_sql(text(str_to_encode)).compile(compile_kwargs={"literal_binds": True})


NodeID = ScalarType(
    "NodeID",
    description="Unique ID for node",
    serialize=str,
    parse_value=from_global_id,
    parse_literal=lambda x: from_global_id(global_id=x.value),
)

NodeInterface = InterfaceType(
    "NodeInterface",
    description="An object with a nodeId",
    fields={
        "nodeId": Field(NonNull(NodeID), description="The global id of the object.", resolver=None)
    },
    # Maybe not necessary
    resolve_type=lambda *args, **kwargs: None,
)
