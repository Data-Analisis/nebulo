# pylint: disable=invalid-name
from __future__ import annotations

import secrets
import string
import typing
from functools import lru_cache

from cachetools import cached
from nebulo.config import Config
from nebulo.gql.alias import CompositeType, ConnectionType, ScalarType, TableType
from nebulo.gql.convert.cursor import to_cursor_sql
from nebulo.gql.convert.node_interface import NodeID, to_global_id_sql
from nebulo.gql.parse_info import ASTNode
from nebulo.sql.inspect import get_columns, get_primary_key_columns, get_relationships, get_table_name
from nebulo.sql.table_base import TableProtocol
from sqlalchemy import Column
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.sql.compiler import StrSQLCompiler


def sanitize(text: str) -> str:
    escape_key = secure_random_string()
    return f"${escape_key}${text}${escape_key}$"


@lru_cache()
def field_name_to_column(sqla_model: TableProtocol, gql_field_name: str) -> Column:
    for column in get_columns(sqla_model):
        if Config.column_name_mapper(column) == gql_field_name:
            return column
    raise Exception(f"No column corresponding to field {gql_field_name}")


@lru_cache()
def field_name_to_relationship(sqla_model: TableProtocol, gql_field_name: str) -> RelationshipProperty:
    for relationship in get_relationships(sqla_model):
        if Config.relationship_name_mapper(relationship) == gql_field_name:
            return relationship
    raise Exception(f"No relationship corresponding to field {gql_field_name}")


def to_join_clause(field: ASTNode, parent_block_name: str) -> typing.List[str]:
    parent_field = field.parent
    assert parent_field is not None
    relation_from_parent = field_name_to_relationship(parent_field.return_type.sqla_model, field.name)
    local_table_name = get_table_name(field.return_type.sqla_model)

    join_clause = []
    for parent_col, local_col in relation_from_parent.local_remote_pairs:
        parent_col_name = parent_col.name
        local_col_name = local_col.name
        join_clause.append(f"{parent_block_name}.{parent_col_name} = {local_table_name}.{local_col_name}")
    return join_clause


def to_pkey_clause(field: ASTNode, pkey_eq: typing.List[str]) -> typing.List[str]:
    local_table = field.return_type.sqla_model
    local_table_name = get_table_name(field.return_type.sqla_model)
    pkey_cols = get_primary_key_columns(local_table)

    res = []
    for col, val in zip(pkey_cols, pkey_eq):
        res.append(f"{local_table_name}.{col.name} = {sanitize(val)}")
    return res


def to_pagination_clause(field: ASTNode) -> str:
    args = field.args
    after_cursor = args.get("after", None)
    before_cursor = args.get("before", None)
    first = args.get("first", None)
    last = args.get("last", None)

    if after_cursor is not None and before_cursor is not None:
        raise ValueError('only one of "before" and "after" may be provided')

    if first is not None and last is not None:
        raise ValueError('only one of "first" and "last" may be provided')

    if after_cursor is not None and last is not None:
        raise ValueError('"after" is not compatible with "last". Use "first"')

    if before_cursor is not None and first is not None:
        raise ValueError('"before" is not compatible with "first". Use "last"')

    if after_cursor is None and before_cursor is None:
        return "true"

    local_table = field.return_type.sqla_model
    local_table_name = get_table_name(field.return_type.sqla_model)
    pkey_cols = get_primary_key_columns(local_table)

    cursor_table, cursor_values = before_cursor or after_cursor
    sanitized_cursor_values = [sanitize(x) for x in cursor_values]

    if cursor_table != local_table_name:
        raise ValueError("Invalid after cursor")

    # No user input
    left = "(" + ", ".join([x.name for x in pkey_cols]) + ")"

    # Contains user input
    right = "(" + ", ".join(sanitized_cursor_values) + ")"

    op = ">" if after_cursor is not None else "<"

    return left + op + right


def to_limit(field: ASTNode) -> int:
    args = field.args
    default = 10
    first = int(args.get("first", default))
    last = int(args.get("last", default))
    limit = min(first, last, default)
    return limit


def to_conditions_clause(field: ASTNode) -> typing.List[str]:
    return_sqla_model = field.return_type.sqla_model
    local_table_name = get_table_name(return_sqla_model)
    args = field.args

    conditions = args.get("condition")

    if conditions is None:
        return ["true"]

    res = []
    for field_name, val in conditions.items():
        column_name = field_name_to_column(return_sqla_model, field_name).name
        res.append(f"{local_table_name}.{column_name} = {sanitize(val)}")
    return res


def build_scalar(field: ASTNode, sqla_model: TableProtocol) -> typing.Tuple[str, typing.Union[str, StrSQLCompiler]]:
    return_type = field.return_type
    if return_type == NodeID:
        return (field.alias, to_global_id_sql(sqla_model))

    column = field_name_to_column(sqla_model, field.name)
    return (field.alias, column.name)


def build_relationship(field: ASTNode, block_name: str) -> typing.Tuple[str, str]:
    return (field.name, sql_builder(field, block_name))


def sql_builder(tree: ASTNode, parent_name: typing.Optional[str] = None) -> str:
    return_type = tree.return_type

    # SQL Function handler
    if hasattr(return_type, "sql_function"):
        return return_type.sql_function.to_executable(tree.args)

    if isinstance(return_type, TableType):
        return row_block(field=tree, parent_name=parent_name)

    if isinstance(return_type, ConnectionType):
        return connection_block(field=tree, parent_name=parent_name)

    raise Exception("sql builder could not match return type")


def sql_finalize(return_name: str, expr: str) -> str:
    return f"""select
    jsonb_build_object('{return_name}', ({expr}))
    """


def row_block(field: ASTNode, parent_name: typing.Optional[str] = None) -> str:
    return_type = field.return_type
    sqla_model = return_type.sqla_model

    block_name = secure_random_string()
    table_name = get_table_name(sqla_model)
    if parent_name is None:
        # If there is no parent, nodeId is mandatory
        _, pkey_eq = field.args["nodeId"]
        pkey_clause = to_pkey_clause(field, pkey_eq)
        join_clause = ["true"]
    else:
        # If there is a parent no arguments are accepted
        join_clause = to_join_clause(field, parent_name)
        pkey_clause = ["true"]

    select_clause = []
    for field in field.fields:
        if isinstance(field.return_type, (ScalarType, CompositeType)):
            select_clause.append(build_scalar(field, sqla_model))
        else:
            select_clause.append(build_relationship(field, block_name))

    block = f"""
(
    with {block_name} as (
        select
            *
        from
            {table_name}
        where
            ({" and ".join(pkey_clause)})
            and ({" and ".join(join_clause)})
    )
    select
        jsonb_build_object({", ".join([f"'{name}', {expr}" for name, expr in select_clause])})
    from
        {block_name}
)
    """
    return block


@cached(cache={}, key=lambda x: x.return_type.sqla_model)
def to_order_clause(field: ASTNode) -> str:
    sqla_model = field.return_type.sqla_model
    return "(" + ", ".join([x.name for x in get_primary_key_columns(sqla_model)]) + ")"


def check_has_total(field: ASTNode) -> bool:
    "Check if 'totalCount' is requested in the query result set"
    return any(x.name in "totalCount" for x in field.fields)


def connection_block(field: ASTNode, parent_name: typing.Optional[str]):
    return_type = field.return_type
    sqla_model = return_type.sqla_model

    block_name = secure_random_string()
    table_name = get_table_name(sqla_model)
    if parent_name is None:
        join_conditions = ["true"]
    else:
        join_conditions = to_join_clause(field, parent_name)

    filter_conditions = to_conditions_clause(field)
    limit = to_limit(field)
    has_total = check_has_total(field)
    order = to_order_clause(field)
    reverse_order = to_order_clause(field) + "desc"

    pagination = to_pagination_clause(field)
    is_page_after = "after" in field.args
    is_page_before = "before" in field.args

    cursor = to_cursor_sql(sqla_model)

    totalCount_alias = field.get_subfield_alias(["totalCount"])

    edges_alias = field.get_subfield_alias(["edges"])
    node_alias = field.get_subfield_alias(["edges", "node"])
    cursor_alias = field.get_subfield_alias(["edges", "cursor"])

    pageInfo_alias = sanitize(field.get_subfield_alias(["pageInfo"]))
    hasNextPage_alias = sanitize(field.get_subfield_alias(["pageInfo", "hasNextPage"]))
    hasPreviousPage_alias = sanitize(field.get_subfield_alias(["pageInfo", "hasPreviousPage"]))
    startCursor_alias = sanitize(field.get_subfield_alias(["pageInfo", "startCursor"]))
    endCursor_alias = sanitize(field.get_subfield_alias(["pageInfo", "endCursor"]))

    edge_node_selects = []
    for cfield in field.fields:
        if cfield.name == "edges":
            for edge_field in cfield.fields:
                if edge_field.name == "node":
                    for subfield in edge_field.fields:
                        # Does anything other than NodeID go here?
                        if isinstance(subfield.return_type, (ScalarType, CompositeType)):
                            elem = build_scalar(subfield, sqla_model)
                        else:
                            elem = build_relationship(subfield, block_name)
                        if cfield.name == "edges":
                            edge_node_selects.append(elem)
                        # Other than edges, pageInfo, and cursor stuff is
                        # all handled by default

    # TODO(OR): Sanitize aliases

    block = f"""
(
    with total as (
        select
            count(*) total_count
        from
            {table_name}
        where
            -- Join Clause
            ({"and".join(join_conditions) or 'true'})
            -- Conditions
            and ({"and".join(filter_conditions) or 'true'})
            -- Skip if not requested
            and {'true' if has_total else 'false'}
    ),

    -- Select table subset with (maybe) 1 extra row
    {block_name}_p1 as (
        select
            *
        from
            {table_name}
        where
            ({"and".join(join_conditions) or 'true'})
            and ({"and".join(filter_conditions) or 'true'})
            and ({pagination})
        order by
            {reverse_order if is_page_before else order},
            {order}
        limit
            {limit + 1}
    ),

    -- Remove possible extra row
    {block_name}_p2 as (
        select
            *
        from
            {block_name}_p1
        limit
            {limit}
    ),

    {block_name} as (
        select
            row_number() over () as _row_num,
            *
        from
            {block_name}_p2
        order by
            {order}
        limit
            {limit}
    ),

    has_next_page as (
        select (select count(*) from {block_name}_p1) > {limit} as has_next
    )

    select
        jsonb_build_object(
            '{totalCount_alias}', (select total_count from total),

            {pageInfo_alias}, jsonb_build_object(
                {hasNextPage_alias}, (select has_next from has_next_page),
                {hasPreviousPage_alias}, {'true' if is_page_after else 'false'},
                {startCursor_alias}, (select {cursor} from {block_name} order by _row_num asc limit 1),
                {endCursor_alias}, (select {cursor} from {block_name} order by _row_num desc limit 1)
            ),
            '{edges_alias}', jsonb_agg(
                jsonb_build_object(
                    '{cursor_alias}', {cursor},
                    '{node_alias}', jsonb_build_object(
                        {", ".join([f"'{name}', {expr}" for name, expr in edge_node_selects])}
                    )
                )
            )
        ) as result
    from
        {block_name}
)
    """

    return block


def secure_random_string(length: int = 8) -> str:
    letters = string.ascii_lowercase
    return "".join([secrets.choice(letters) for _ in range(length)])
