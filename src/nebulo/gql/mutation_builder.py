# pylint: disable=invalid-name
from __future__ import annotations

from nebulo.config import Config
from nebulo.gql.parse_info import ASTNode
from nebulo.gql.query_builder import field_name_to_column
from nebulo.gql.relay.node_interface import to_node_id_sql
from nebulo.sql.inspect import get_primary_key_columns


def build_insert(tree: ASTNode):
    return_type = tree.return_type
    # Find the table type
    return_sqla_model = return_type.sqla_model
    table_input_arg_name = Config.table_name_mapper(return_sqla_model)
    input_values = tree.args["input"][table_input_arg_name]
    col_name_to_value = {}
    for arg_name, arg_value in input_values.items():
        col = field_name_to_column(return_sqla_model, arg_name)
        col_name_to_value[col.name] = arg_value

    core_table = return_sqla_model.__table__

    query = (
        core_table.insert()
        .values(**col_name_to_value)
        .returning(to_node_id_sql(return_sqla_model, core_table).label("nodeId"))
    )
    return query


def build_update(tree: ASTNode):
    return_type = tree.return_type
    sqla_model = return_type.sqla_model

    # Where Clause
    pkey_cols = get_primary_key_columns(sqla_model)
    node_id = tree.args["nodeId"]
    pkey_clause = [col == node_id.values[str(col.name)] for col in pkey_cols]

    # Find the table type
    return_sqla_model = return_type.sqla_model
    table_input_arg_name = Config.table_name_mapper(return_sqla_model)
    input_values = tree.args["input"][table_input_arg_name]
    col_name_to_value = {}
    for arg_name, arg_value in input_values.items():
        col = field_name_to_column(return_sqla_model, arg_name)
        col_name_to_value[col.name] = arg_value

    core_table = return_sqla_model.__table__

    query = (
        core_table.update()
        .where(*pkey_clause)
        .values(**col_name_to_value)
        .returning(to_node_id_sql(return_sqla_model, core_table).label("nodeId"))
    )
    return query
