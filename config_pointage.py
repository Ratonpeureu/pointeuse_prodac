import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import time

class PauseMode(Enum):
    """Qui gère les pauses ?"""
    TERMINAL = "terminal"          # La pointeuse envoie pause/fin_pause
    SYSTEM = "system"              # Système = 1er arrivée + dernier départ
    HYBRID = "hybrid"              # Terminal peut envoyer, sinon système

class PointageMode(Enum):
    """Règle de gestion des re-badgeages"""
    FIRST_ONLY = "first_only"      # 1ère arrivée = finale (autres ignorées)
    LAST_ONLY = "last_only"        # Dernier départ = final
    ALLOW_MULTIPLE = "allow_multiple"  # Tous les badgeages enregistrés

class DataFormat(Enum):
    """Format reçu du terminal"""
    CSV = "csv"
    JSON = "json"
    BINARY = "binary"

@dataclass
class TerminalDataConfig:
    """Structure = comment le terminal renvoie les données"""
    format: str = "csv"                    # csv | json | binary
    delimiter: str = ","
    encoding: str = "utf-8"
    fields: List[str] = field(default_factory=lambda: [
        "id_pointeuse",     # 0
        "timestamp",        # 1
        "action",           # 2
        "statut_badge",     # 3
        "extra_1",          # 4
        "extra_2",          # 5
    ])
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    
    # Mapping personnalisé si les champs arrivent dans un ordre différent
    field_mapping: Dict[str, int] = field(default_factory=lambda: {
        "id_pointeuse": 0,
        "timestamp": 1,
        "action": 2,
        "statut_badge": 3,
        "extra_1": 4,
        "extra_2": 5,
    })

@dataclass
class PauseConfig:
    """Gestion des pauses"""
    mode: str = "terminal"              # terminal | system | hybrid
    default_duration_min: int = 60      # Si pas de signal fin_pause
    allow_variable_pause: bool = True   # Pause peut varier jour/jour ?
    warn_if_over_min: int = 15          
    warn_if_under_min: int = 10         

@dataclass
class PointageConfig:
    """Règles de gestion des pointages"""
    mode_arrivee: str = "first_only"           # first_only | last_only
    mode_depart: str = "last_only"             # Toujours dernier départ
    allow_rebadge_same_day: bool = False       # Peut re-badger même jour ?
    ignore_rebadge_within_min: int = 5         # Ignorer re-badges < 5 min
    log_all_attempts: bool = True              # Logger même les ignorés

@dataclass
class NetworkConfig:
    """Configuration réseau"""
    host: str = "0.0.0.0"
    port: int = 9999
    timeout_client_sec: int = 300         # Déconnexion après 5min inactivité
    max_concurrent_clients: int = 50
    buffer_size: int = 4096

@dataclass
class LogConfig:
    """Configuration des logs"""
    level: str = "INFO"                   # DEBUG | INFO | WARNING | ERROR
    format: str = "structured"             # structured | simple | json
    output: str = "both"                   # console | file | both
    file_path: str = "./logs/pointage.log"
    max_file_size_mb: int = 100
    backup_count: int = 5
    # Pour l'interface de suivi
    keep_in_memory_records: int = 1000    # Garder 1000 derniers events en mém

@dataclass
class EnterpriseConfig:
    """Config spécifique à l'entreprise"""
    enterprise_id: str = "default"
    name: str = "Entreprise"
    timezone: str = "Africa/Dakar"
    working_days: List[int] = field(default_factory=lambda: [0,1,2,3,4])  # Lun-Ven = 0-4
    
    # Actions reconnues + leur mapping
    action_codes: Dict[int, str] = field(default_factory=lambda: {
        0: "arrivee",
        1: "pause",
        2: "fin_pause",
        3: "depart",
    })
    
    # Horaires par défaut si pas de planning
    default_schedule_start: str = "08:00"
    default_schedule_end: str = "17:00"
    default_break_duration_min: int = 60

class PointageConfigManager:
    """Charge la config depuis env + fichier + defaults"""
    
    def __init__(self):
        self.terminal_data = TerminalDataConfig(
            format=os.getenv("TERMINAL_FORMAT", "csv"),
            delimiter=os.getenv("TERMINAL_DELIMITER", ","),
            encoding=os.getenv("TERMINAL_ENCODING", "utf-8"),
            timestamp_format=os.getenv("TERMINAL_TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S"),
        )
        
        self.pause = PauseConfig(
            mode=os.getenv("PAUSE_MODE", "terminal"),
            default_duration_min=int(os.getenv("PAUSE_DEFAULT_MIN", 60)),
            allow_variable_pause=os.getenv("PAUSE_VARIABLE", "true").lower() == "true",
            warn_if_over_min=int(os.getenv("PAUSE_WARN_OVER_MIN", 15)),
            warn_if_under_min=int(os.getenv("PAUSE_WARN_UNDER_MIN", 10)),
        )
        
        self.pointage = PointageConfig(
            mode_arrivee=os.getenv("POINTAGE_ARRIVEE_MODE", "first_only"),
            mode_depart=os.getenv("POINTAGE_DEPART_MODE", "last_only"),
            allow_rebadge_same_day=os.getenv("ALLOW_REBADGE", "false").lower() == "true",
            ignore_rebadge_within_min=int(os.getenv("REBADGE_IGNORE_MIN", 5)),
            log_all_attempts=os.getenv("LOG_ALL_ATTEMPTS", "true").lower() == "true",
        )
        
        self.network = NetworkConfig(
            host=os.getenv("TERMINAL_HOST", "0.0.0.0"),
            port=int(os.getenv("TERMINAL_PORT", 9999)),
            timeout_client_sec=int(os.getenv("CLIENT_TIMEOUT_SEC", 300)),
            max_concurrent_clients=int(os.getenv("MAX_CLIENTS", 50)),
        )
        
        self.log = LogConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format=os.getenv("LOG_FORMAT", "structured"),
            output=os.getenv("LOG_OUTPUT", "both"),
            file_path=os.getenv("LOG_FILE", "./logs/pointage.log"),
            keep_in_memory_records=int(os.getenv("LOG_MEMORY_RECORDS", 1000)),
        )
        
        self.enterprise = EnterpriseConfig() 
    
    def load_custom_field_mapping(self, mapping_str: str):
        """Charge un mapping custom : '{"id_pointeuse": 0, "timestamp": 1, ...}'"""
        import json
        try:
            self.terminal_data.field_mapping = json.loads(mapping_str)
        except json.JSONDecodeError:
            print(f" Invalid field mapping JSON: {mapping_str}")


# Instance globale
config = PointageConfigManager()