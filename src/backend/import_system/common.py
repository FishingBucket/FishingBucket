from abc import ABC, abstractmethod
from collections import defaultdict

from ..database.user import UserID
from ..models import ProxyTag, ID, FullProxy


class Importer(ABC):
    def __init__(self):
        self.proxies: list[FullProxy] = []
        self.tags: list[ProxyTag] = []
        self.relationships: dict[ID, list[ID]] = defaultdict(list)

    @abstractmethod
    def import_data(self, data: bytes, owner: UserID): pass

    @staticmethod
    def sanitize_potential_template_fragment(fragment: str) -> str:
        return fragment.replace("{", "\\{").replace("}", "\\}")


class Exporter(ABC):
    def __init__(self, proxies: list[FullProxy], tags: list[ProxyTag], relationships: dict[ID, list[ID]]):
        self.proxies = proxies
        self.tags = tags
        self.relationships: dict[ID, list[ID]] = relationships

    @abstractmethod
    def export_data(self) -> bytes: pass

    @property
    @abstractmethod
    def filename(self) -> str: pass
