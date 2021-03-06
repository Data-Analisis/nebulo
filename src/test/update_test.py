import json

from nebulo.gql.relay.node_interface import NodeIdStructure

SQL_UP = """
CREATE TABLE account (
    id serial primary key,
    name text not null,
    created_at timestamp without time zone default (now() at time zone 'utc')
);

INSERT INTO account (id, name) VALUES
(1, 'oliver'),
(2, 'rachel'),
(3, 'sophie');
"""


def test_update_mutation(client_builder):
    client = client_builder(SQL_UP)
    account_id = 1
    node_id = NodeIdStructure(table_name="account", values={"id": account_id}).serialize()
    query = f"""

mutation {{
  updateAccount(input: {{
    clientMutationId: "gjwl"
    nodeId: "{node_id}"
    account: {{
      name: "Buddy"
    }}
  }}) {{
    clientMutationId
    account {{
      dd: id
      nodeId
      name
    }}
  }}
}}
    """

    with client:
        resp = client.post("/", json={"query": query})
    assert resp.status_code == 200
    payload = json.loads(resp.text)
    assert isinstance(payload["data"]["updateAccount"]["account"], dict)
    assert payload["data"]["updateAccount"]["account"]["dd"] == account_id
    assert payload["data"]["updateAccount"]["account"]["nodeId"] == node_id
    assert payload["data"]["updateAccount"]["account"]["name"] == "Buddy"
    assert payload["data"]["updateAccount"]["clientMutationId"] == "gjwl"
    assert len(payload["errors"]) == 0
