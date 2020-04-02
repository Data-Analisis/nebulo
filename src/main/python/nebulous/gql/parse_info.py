import typing

from graphql.execution.values import get_argument_values

from nebulous.gql.alias import Field, List, NonNull, ResolveInfo

__all__ = ["parse_resolve_info"]


def field_to_type(field):
    """Recursively unwraps nested Field, List, and NonNull
    qualifiers to a concrete GraphQL Type"""
    if isinstance(field, Field):
        return field_to_type(field.type)
    if isinstance(field, List):
        return field_to_type(field.of_type)
    if isinstance(field, NonNull):
        return field_to_type(field.of_type)
    return field


class ASTNode:
    def __init__(self, field_ast, field_def, schema, parent: "ASTNode"):
        args = get_argument_values(arg_defs=field_def.args, arg_asts=field_ast.arguments)
        selection_set = field_ast.selection_set
        field_type = field_to_type(field_def)

        self.alias = field_ast.alias or field_ast.name.value
        self.name = field_ast.name.value
        self.return_type = field_type
        self.parent: ASTNode = parent
        self.args = args
        self.path = parent.path + [self.name] if parent is not None else ["root"]

        print(self.path)

        sub_fields = []
        if selection_set:
            for selection_ast in selection_set.selections:
                selection_name = selection_ast.name.value
                selection_field = field_type.fields[selection_name]
                sub_fields.append(ASTNode(selection_ast, selection_field, schema, parent=self))

        self.fields = sub_fields


def parse_resolve_info(info: ResolveInfo) -> typing.Dict:
    """Converts execution ResolveInfo into a dictionary
    hierarchy

    {
        "alias": *alias*,
        "name": *name*,
        "return_type": *return_type*,
        "args":  {
            "first": 10
        },
        "parent": <reference to parent field or None>
        "fields": [
            # Same structure again, for each field selected
            # in the query
            {
                "alias": ...
                "name": ...
            }
        }
    }
    """
    # Root info
    field_ast = info.field_asts[0]
    schema = info.schema

    # Current field from parent
    parent_type = info.parent_type
    parent_lookup_name = field_ast.name.value
    current_field = parent_type.fields[parent_lookup_name]
    parsed_info = ASTNode(field_ast, current_field, schema, parent=None)
    return parsed_info
