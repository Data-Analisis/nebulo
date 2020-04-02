# pylint: disable=comparison-with-callable
from __future__ import annotations

import typing

from nebulous.sql.inspect import get_table_name
from nebulous.text_utils.base64 import from_base64, to_base64, to_base64_sql
from sqlalchemy import asc, desc, text

from ..alias import CursorType

__all__ = ["Cursor"]


if typing.TYPE_CHECKING:
    pass


DIRECTION_TO_STR = {asc: "asc", desc: "desc"}
STR_TO_DIRECTION = {v: k for k, v in DIRECTION_TO_STR.items()}


def from_cursor(
    cursor: str,
) -> typing.Tuple[str, typing.List[str], typing.List[typing.Tuple[str, "asc/desc"]]]:
    """Parses a cursor from form
    offer[id:desc,age:asc](4)
    """
    # offer@1,5
    cursor_str = from_base64(cursor)

    # e.g. 'offer'
    sqla_model_name, remain = cursor_str.split("@", 1)

    # e.g. 'id:desc,age:asc'
    values = [x for x in remain.split(",") if x]
    return sqla_model_name, values


Cursor = CursorType(
    "Cursor", serialize=str, parse_value=from_cursor, parse_literal=lambda x: from_cursor(x.value)
)


def to_cursor(table_name, values: typing.List[typing.Any]) -> str:
    str_to_encode = f"'{table_name}@" + ", ".join([str(x) for x in values])
    return to_base64(str_to_encode)


def to_cursor_sql(sqla_model) -> "sql_selector":
    table_name = get_table_name(sqla_model)
    pkey_cols = list(sqla_model.__table__.primary_key.columns)

    selector = ", ||".join([f'"{col.name}"' for col in pkey_cols])

    str_to_encode = f"'{table_name}' || '@' || " + selector

    return to_base64_sql(text(str_to_encode)).compile(compile_kwargs={"literal_binds": True})
