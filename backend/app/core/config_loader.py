from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"


class ConfigLoader:
    def __init__(self, config_dir: Path = CONFIG_DIR):
        self.config_dir = config_dir

    def _read_yaml(self, filename: str) -> Dict[str, Any]:
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def bots(self) -> List[Dict[str, Any]]:
        return self._read_yaml("bots.yaml").get("bots", [])

    def advertising_companies(self) -> List[Dict[str, Any]]:
        return self._read_yaml("advertising_companies.yaml").get("advertising_companies", [])

    def data_sources(self) -> Dict[str, Any]:
        return self._read_yaml("data_sources.yaml").get("data_sources", {})

    def advertising_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        for entry in self.advertising_companies():
            if entry.get("company_id") == company_id:
                return entry
        return None
