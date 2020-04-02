from __future__ import annotations

from typing import TYPE_CHECKING

from .alias import ObjectType, Schema
from .entrypoints.single_node import single_node_factory

if TYPE_CHECKING:
    from nebulous.sql.sql_database import SQLDatabase
    from nebulous.user_config import UserConfig


class GQLDatabase:
    def __init__(self, sqldb: SQLDatabase, config: UserConfig):
        self.config = config

        # GQL Tables
        self.sqldb = sqldb

        # self.gql_models: List[GraphQLObjectType] = [convert_table(x) for x in sqldb.models]
        # self.gql_functions: List[ReflectedGQLFunction] = [
        #    function_reflection_factory(x) for x in sqldb.functions
        # ]

        # GQL Schema
        self.schema = Schema(self.query_object())

    def query_object(self):
        """Creates a base query object from available graphql objects/tables"""
        # query_fields = {
        #
        # }

        query_fields = {
            **{f"{x.__table__.name}": single_node_factory(x) for x in self.sqldb.models},
            # **{
            #    f"all{pascalcase(x.__table__.name)}s": Connection(x).field()
            #    for x in self.sqldb.models
            # },
        }

        query_object = ObjectType(name="Query", fields=lambda: query_fields)
        return query_object