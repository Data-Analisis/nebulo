from __future__ import annotations

import typing
from functools import lru_cache

from ..alias import (
    Argument,
    EnumType,
    EnumValue,
    Field,
    InputField,
    InputObjectType,
    Int,
    List,
    NonNull,
    ObjectType,
)
from ..casing import snake_to_camel

if typing.TYPE_CHECKING:
    from nebulous.sql.table_base import TableBase

__all__ = ["condition_factory"]


@lru_cache()
def condition_factory(sqla_model: TableBase) -> InputObjectType:
    from nebulous.gql.convert.table import convert_column

    result_name = f"{snake_to_camel(sqla_model.__table__.name)}Condition"
    attrs = {}
    for column in sqla_model.columns:
        attrs[column.name] = convert_column(column, output_type=InputField)
    return InputObjectType(result_name, attrs, description="", container_type=None)
