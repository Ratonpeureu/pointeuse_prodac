
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pointage_prodac.config_pointage import config
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from dotenv import load_dotenv
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class PointageEvent:
    """Event universel"""
    id_pointeuse: str
    timestamp: datetime
    action: int
    action_name: str
    statut_badge: int
    extra_data: Dict[str, Any]
    received_at: datetime  

class TerminalDataParser:
    """Parser universel pour CSV | JSON | BINARY"""
    
    CONFIG = config.terminal_data
    ACTION_MAP = config.enterprise.action_codes
    
    @classmethod
    def parse(cls, raw_data: str) -> Optional[PointageEvent]:
        """Route vers le bon parser"""
        fmt = cls.CONFIG.format.lower()
        
        if fmt == "csv":
            return cls._parse_csv(raw_data)
        elif fmt == "json":
            return cls._parse_json(raw_data)
        elif fmt == "binary":
            return cls._parse_binary(raw_data)
        else:
            logger.error(f" format: {fmt}")
            return None
    
    
    @classmethod
    def _parse_csv(cls, raw_line: str) -> Optional[PointageEvent]:
        try:
            parts = raw_line.strip().split(cls.CONFIG.delimiter)
            mapping = cls.CONFIG.field_mapping

            # Vérifier que les indices nécessaires sont présents
            required = ["id_pointeuse", "timestamp", "action", "statut_badge"]
            for key in required:
                idx = mapping.get(key)
                if idx is None or idx >= len(parts):
                    logger.warning(f"Champ {key} manquant dans: {raw_line}")
                    return None

            id_pointeuse = parts[mapping["id_pointeuse"]].strip()
            timestamp_str = parts[mapping["timestamp"]].strip()
            action = int(parts[mapping["action"]])
            statut_badge = int(parts[mapping["statut_badge"]])

            # Champs optionnels
            extra_data = {}
            for extra_key in ["extra_1", "extra_2"]:
                idx = mapping.get(extra_key)
                if idx is not None and idx < len(parts):
                    extra_data[extra_key] = parts[idx].strip()

            timestamp = datetime.strptime(timestamp_str, cls.CONFIG.timestamp_format)
            action_name = cls.ACTION_MAP.get(action, f"unknown_{action}")

            return PointageEvent(
                id_pointeuse=id_pointeuse,
                timestamp=timestamp,
                action=action,
                action_name=action_name,
                statut_badge=statut_badge,
                extra_data=extra_data,
                received_at=datetime.now(),
            )
        except (ValueError, IndexError) as e:
            logger.error(f"Erreur parsing '{raw_line}': {e}")
            return None

    @classmethod
    def _parse_json(cls, raw_json: str) -> Optional[PointageEvent]:
        """Parse JSON"""
        try:
            data = json.loads(raw_json)
            
            id_pointeuse = data.get("id_pointeuse") or data.get("terminal_id") or data.get("id")
            timestamp_str = data.get("timestamp") or data.get("time")
            action = data.get("action") if data.get("action") is not None else data.get("event")
            
            if not all([id_pointeuse, timestamp_str, action is not None]):
                logger.warning(f"JSON incompleted: {raw_json}")
                return None
            
            timestamp = datetime.fromisoformat(timestamp_str)
            action = int(action)
            action_name = cls.ACTION_MAP.get(action, f"unknown_{action}")
            
            return PointageEvent(
                id_pointeuse=str(id_pointeuse),
                timestamp=timestamp,
                action=action,
                action_name=action_name,
                statut_badge=data.get("statut_badge", 0),
                extra_data={k: v for k, v in data.items() 
                           if k not in ["id_pointeuse", "timestamp", "action"]},
                received_at=datetime.now(),
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"jSON invalide: {e}")
            return None
    
    @classmethod
    def _parse_binary(cls, raw_bytes: bytes) -> Optional[PointageEvent]:
        logger.warning("........B")
        return None





class TerminalSocketServer:

    
    def __init__(
        self,
        host: str = "0.0.0.0", #Ici dans votre reseau definissez quels address est branche votrer terminal de pointages
        port: int = 9999, # laaussi mais y'a un port par default a moins que vous ne le changiez
        on_pointage_event: callable = None,
    ):
        self.host = host
        self.port = port
        self.on_pointage_event = on_pointage_event  
        self._server: Optional[asyncio.AbstractServer] = None
        self._clients: set = set()
    
    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Gère une connexion entrante d'un terminal Fictif //ici c'est a des fins de test uniquemment """
        addr = writer.get_extra_info("peername")
        logger.info(f"Nouveau terminal connecté: {addr}")
        self._clients.add(writer)
        
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break  # connexion fermée
                
                line = data.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                
                logger.debug(f"Reçu du terminal {addr}: {line}")
                
                # Parser l'events ///
                event = TerminalDataParser.parse(line)

                if event is None:
                    continue
                
                if self.on_pointage_event:
                    await self.on_pointage_event(event)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Erreur avec le terminal {addr}: {e}")
        finally:
            logger.info(f"Terminal déconnecté: {addr}")
            self._clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
    
    async def start(self):
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        addr = self._server.sockets[0].getsockname()
        logger.info(f"Serveur ecoute terminaux  sur {addr}")
        print(f" ecoute sur {self.host}:{self.port}")
        
    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for writer in list(self._clients):
            writer.close()
        logger.info("écoute terminal fini")





