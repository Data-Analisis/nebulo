from __future__ import annotations
from typing import TYPE_CHECKING
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine

if TYPE_CHECKING:
    from csql.user_config import UserConfig


class SQLDatabase:
    def __init__(self, config: UserConfig):
        # Configure SQLAlchemy
        self.engine = create_engine(config.connection, echo=config.echo_queries)
        self.base = automap_base()
        self.base.prepare(self.engine, reflect=True, schema=config.schema)
        self.session = scoped_session(sessionmaker(bind=self.engine))

        # SQLA Tables
        self.models = list(self.base.classes)
