from dataclasses import dataclass

from ..backend.config import Config_
from ..backend.database.database import Database


@dataclass
class ApplicationContext:
    database: Database
    config: Config_
