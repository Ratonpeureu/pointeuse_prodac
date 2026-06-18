# logger_pointage.py

import logging
import json
from datetime import datetime
from typing import Dict, Any
from collections import deque
from pointage_prodac.config_pointage import config
import logging.handlers
class StructuredFormatter(logging.Formatter):
    """Formate les logs en JSON"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Ajouter les extras
        if hasattr(record, "event_id"):
            log_data["event_id"] = record.event_id
        if hasattr(record, "employe_id"):
            log_data["employe_id"] = record.employe_id
        if hasattr(record, "action"):
            log_data["action"] = record.action
        
        return json.dumps(log_data, ensure_ascii=False)

class PointageLogManager:
    """Gère les logs + stockage mémoire pour suivi temps réel"""
    
    def __init__(self):
        self.config = config.log
        self.logger = logging.getLogger("pointage")
        self.setup_handlers()
        
        # Stockage en mémoire des derniers événements
        self.events_buffer = deque(maxlen=self.config.keep_in_memory_records)
    
    def setup_handlers(self):
        """Configure les handlers selon la config"""
        self.logger.setLevel(self.config.level)
        
        if self.config.format == "structured":
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        
        # Console
        if self.config.output in ["console", "both"]:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
        
        # Fichier
        if self.config.output in ["file", "both"]:
            try:
                import os
                log_dir = os.path.dirname(self.config.file_path) or "."
                os.makedirs(log_dir, exist_ok=True)
                fh = logging.handlers.RotatingFileHandler(
                    self.config.file_path,
                    maxBytes=self.config.max_file_size_mb * 1024 * 1024,
                    backupCount=self.config.backup_count,
                )
                fh.setFormatter(formatter)
                self.logger.addHandler(fh)
            except Exception as e:
                print(f"Impossible creer log: {e}")

    def log_pointage(
        self,
        employe_id: str,
        employe_name: str,
        action: str,
        heure: str,
        statut: str,
        message: str,
        warning: str = None,
    ):
        """Log un événement de pointage"""
        event_record = {
            "timestamp": datetime.now().isoformat(),
            "employe_id": employe_id,
            "employe_name": employe_name,
            "action": action,
            "heure": heure,
            "statut": statut,
            "message": message,
            "warning": warning,
        }
        
        # Stocker en buffer
        self.events_buffer.append(event_record)
        
        # Logger
        log_message = f"[{employe_name}] {action} → {heure} | {message}"
        if warning:
            self.logger.warning(log_message + f" ⚠️ {warning}")
        else:
            self.logger.info(log_message)
    
    def get_recent_events(self, limit: int = 50) -> list:
        """Retourne les N derniers événements (pour WebSocket)"""
        return list(self.events_buffer)[-limit:]

# Instance globale
log_manager = PointageLogManager()