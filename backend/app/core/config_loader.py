from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Читает статичные YAML-конфиги из папки config/ в корне монорепо.
# Используется при первичной ингестии для загрузки реестра ботов и компаний.
ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"


class ConfigLoader:
    """Загрузчик YAML-конфигов (боты, рекламные компании, источники данных)."""

    def __init__(self, config_dir: Path = CONFIG_DIR):
        self.config_dir = config_dir

    def _read_yaml(self, filename: str) -> Dict[str, Any]:
        """Читает YAML-файл из config_dir. Возвращает пустой dict если файл отсутствует."""
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def bots(self) -> List[Dict[str, Any]]:
        """Список всех ботов из config/bots.yaml."""
        return self._read_yaml("bots.yaml").get("bots", [])

    def advertising_companies(self) -> List[Dict[str, Any]]:
        """Список рекламных компаний из config/advertising_companies.yaml."""
        return self._read_yaml("advertising_companies.yaml").get("advertising_companies", [])

    def data_sources(self) -> Dict[str, Any]:
        """Конфиг источников данных (БД для репликации) из config/data_sources.yaml."""
        return self._read_yaml("data_sources.yaml").get("data_sources", {})

    def advertising_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Находит конфиг одной компании по её company_id. Возвращает None если не найдена."""
        for entry in self.advertising_companies():
            if entry.get("company_id") == company_id:
                return entry
        return None
