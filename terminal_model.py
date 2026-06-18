# terminal_models.py
# Base de données pré-configurée de terminaux biométriques
# Simplifie la configuration pour l'informaticien

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class DataFormat(Enum):
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    BINARY = "binary"

@dataclass
class TerminalModel:
    """Configuration pré-configurée d'un modèle de terminal"""
    name: str
    manufacturer: str
    port: int
    protocol: str  # TCP, HTTP, RS232, etc
    data_format: DataFormat
    delimiter: Optional[str] = ","
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    field_mapping: Dict[str, int] = None
    example_data: str = ""
    notes: str = ""
    documentation_url: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "port": self.port,
            "protocol": self.protocol,
            "data_format": self.data_format.value,
            "delimiter": self.delimiter,
            "timestamp_format": self.timestamp_format,
            "field_mapping": self.field_mapping,
            "example_data": self.example_data,
            "notes": self.notes,
            "documentation_url": self.documentation_url,
        }
    
    def to_env_config(self) -> Dict[str, str]:
        """Génère les variables d'environnement pour ce modèle"""
        config = {
            "TERMINAL_FORMAT": self.data_format.value,
            "TERMINAL_HOST": "0.0.0.0",
            "TERMINAL_PORT": str(self.port),
        }
        
        if self.delimiter:
            config["TERMINAL_DELIMITER"] = self.delimiter
        
        config["TERMINAL_TIMESTAMP_FORMAT"] = self.timestamp_format
        
        if self.field_mapping:
            import json
            config["TERMINAL_FIELD_MAPPING"] = json.dumps(self.field_mapping)
        
        return config


# ═══════════════════════════════════════════════════════════════════════
# CATALOGUE DES TERMINAUX BIOMÉTRIQUES
# ═══════════════════════════════════════════════════════════════════════

TERMINAL_MODELS = {
    "zkteco_k14": TerminalModel(
        name="ZKTeco K14 Standalone Time Attendance Terminal",
        manufacturer="ZKTeco",
        port=23,  # Telnet par défaut
        protocol="TCP/Telnet",
        data_format=DataFormat.CSV,
        delimiter=",",
        timestamp_format="%Y-%m-%d %H:%M:%S",
        field_mapping={
            "id_pointeuse": 0,      # PIN/ID employé
            "timestamp": 1,          # Date/heure
            "action": 2,             # 0=arrivée, 1=pause, 3=départ
            "statut_badge": 3,       # 0=OK, 1=Erreur
            "device_id": 4,          # ID du terminal
        },
        example_data="12345,2026-06-18 08:30:15,0,0,K14001",
        notes="Export via Telnet ou USB. Supporte FTP pour export automatique.",
        documentation_url="https://www.zkteco.com/en/product/K-Series.html"
    ),
    
    "hikvision_ds_k1a8503ef": TerminalModel(
        name="Hikvision DS-K1A8503EF Fingerprint Time Attendance Terminal",
        manufacturer="Hikvision",
        port=8080,  # HTTP par défaut
        protocol="HTTP/REST API",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%dT%H:%M:%S",
        field_mapping={
            "id_pointeuse": "personId",
            "timestamp": "createTime",
            "action": "deviceEvent",
            "statut_badge": "status",
        },
        example_data='{"personId":"12345","createTime":"2026-06-18T08:30:15","deviceEvent":"entry","status":"0"}',
        notes="API REST natif. Authentification OAuth2 recommandée. Export logs en HTTP PUT/POST.",
        documentation_url="https://www.hikvision.com/en/products/Biometric-Access-Control/"
    ),
    
    "zkteco_iface950": TerminalModel(
        name="ZKTeco iFace950 Multi-Biometric Terminal",
        manufacturer="ZKTeco",
        port=3306,  # MySQL/MariaDB direct ou 8888 pour API
        protocol="HTTP/API ou MySQL",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%d %H:%M:%S",
        field_mapping={
            "id_pointeuse": "PIN",
            "timestamp": "PunchTime",
            "action": "PunchState",
            "statut_badge": "Status",
            "device_id": "DeviceID",
        },
        example_data='{"PIN":"12345","PunchTime":"2026-06-18 08:30:15","PunchState":0,"Status":1,"DeviceID":"IFACE950_001"}',
        notes="Supporte HTTP API, MySQL direct, ou SD Card CSV export. Multi-biométrique (empreinte/visage/iris).",
        documentation_url="https://www.zkteco.com/en/product/iFace-Series.html"
    ),
    
    "kelio_visio_x7": TerminalModel(
        name="Kelio Visio X7 Terminal Tactile Biométrique",
        manufacturer="Kelio (Groupe Safran)",
        port=9998,  # TCP propriétaire
        protocol="TCP/Proprietary",
        data_format=DataFormat.XML,
        timestamp_format="%Y-%m-%d %H:%M:%S",
        field_mapping=None,  # Format XML, pas de mapping simple
        example_data='''<Attendance>
  <PersonId>12345</PersonId>
  <Timestamp>2026-06-18 08:30:15</Timestamp>
  <EventType>Entry</EventType>
  <TerminalId>X7_001</TerminalId>
</Attendance>''',
        notes="Format XML. Nécessite parser spécifique. Interface tactile 7 pouces. Français-friendly.",
        documentation_url="https://www.kelio.com/produits/controle-acces/visio-x7/"
    ),
    
    "zkteco_f18": TerminalModel(
        name="ZKTeco F18 Biometric Fingerprint Access Control Terminal",
        manufacturer="ZKTeco",
        port=23,  # Telnet
        protocol="TCP/Telnet ou HTTP API",
        data_format=DataFormat.CSV,
        delimiter=",",
        timestamp_format="%Y-%m-%d %H:%M:%S",
        field_mapping={
            "id_pointeuse": 0,
            "timestamp": 1,
            "action": 2,
            "statut_badge": 3,
            "door_id": 4,
        },
        example_data="12345,2026-06-18 08:30:15,0,1,DOOR_A",
        notes="Entrée/sortie par empreinte digitale. Export via USB ou FTP.",
        documentation_url="https://www.zkteco.com/en/product/F-Series.html"
    ),
    
    "idemia_morphoaccess_sigma": TerminalModel(
        name="Idemia MorphoAccess SIGMA Lite Series Fingerprint Terminal",
        manufacturer="Idemia",
        port=443,  # HTTPS/REST
        protocol="HTTPS/REST API",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%dT%H:%M:%SZ",
        field_mapping={
            "id_pointeuse": "userId",
            "timestamp": "eventTimestamp",
            "action": "eventType",
            "statut_badge": "verificationStatus",
        },
        example_data='{"userId":"12345","eventTimestamp":"2026-06-18T08:30:15Z","eventType":"AccessGranted","verificationStatus":"Successful"}',
        notes="Sécurité renforcée (Idemia=THALES). API REST avec OAuth2 obligatoire. Excellent pour gouvernance.",
        documentation_url="https://www.idemia.com/access-control"
    ),
    
    "zkteco_speedface_v5l": TerminalModel(
        name="ZKTeco SpeedFace-V5L Touchless Recognition Terminal",
        manufacturer="ZKTeco",
        port=8888,  # HTTP API
        protocol="HTTP/REST API",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%dT%H:%M:%S",
        field_mapping={
            "id_pointeuse": "personId",
            "timestamp": "recognitionTime",
            "action": "accessEvent",
            "statut_badge": "status",
            "temperature": "bodyTemperature",
            "mask_detected": "maskDetected",
        },
        example_data='{"personId":"12345","recognitionTime":"2026-06-18T08:30:15","accessEvent":"in","status":"success","bodyTemperature":36.8,"maskDetected":false}',
        notes="Reconnaissance faciale sans contact. COVID-friendly. Température intégrée. API REST moderne.",
        documentation_url="https://www.zkteco.com/en/product/SpeedFace-series.html"
    ),
    
    "suprema_biostation_2": TerminalModel(
        name="Suprema BioStation 2 Ultra Performance Fingerprint Terminal",
        manufacturer="Suprema",
        port=9098,  # Suprema propriétaire
        protocol="TCP/Suprema BioStar API",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%d %H:%M:%S",
        field_mapping={
            "id_pointeuse": "userID",
            "timestamp": "eventTime",
            "action": "eventType",
            "statut_badge": "verificationResult",
            "image_b64": "fingerPrintImage",
        },
        example_data='{"userID":"12345","eventTime":"2026-06-18 08:30:15","eventType":"1","verificationResult":"Success"}',
        notes="Performance ultra (2000 doigts/sec). Lecteur 500MP. Supporte stockage images. Nécessite BioStar SDK.",
        documentation_url="https://www.supremainc.com/en/products/time-attendance/"
    ),
    
    "anviz_ep300": TerminalModel(
        name="Anviz EP300 Fingerprint Time Attendance Terminal",
        manufacturer="Anviz",
        port=502,  # Modbus TCP
        protocol="Modbus TCP ou HTTP",
        data_format=DataFormat.CSV,
        delimiter="|",
        timestamp_format="%d-%m-%Y %H:%M:%S",
        field_mapping={
            "id_pointeuse": 0,
            "timestamp": 1,
            "action": 2,
            "statut_badge": 3,
        },
        example_data="12345|18-06-2026 08:30:15|0|1",
        notes="Support Modbus pour intégration SCADA. Délimiteur pipe |. Très industriel.",
        documentation_url="https://www.anviz.com/en/product_list/102.html"
    ),
    
    "hikvision_generic": TerminalModel(
        name="Hikvision - Modèle générique (Configurateur manuel)",
        manufacturer="Hikvision",
        port=8080,
        protocol="HTTP/REST API",
        data_format=DataFormat.JSON,
        timestamp_format="%Y-%m-%dT%H:%M:%S",
        field_mapping={},
        example_data='{"personId":"","createTime":"","accessType":""}',
        notes="Configuration manuelle requise. Consulter documentation du modèle spécifique.",
        documentation_url="https://www.hikvision.com/en/support/"
    ),
}

# Mapping par code court
TERMINAL_SHORTCUTS = {
    "zk_k14": "zkteco_k14",
    "hik_k1a8503": "hikvision_ds_k1a8503ef",
    "zk_iface950": "zkteco_iface950",
    "kelio_x7": "kelio_visio_x7",
    "zk_f18": "zkteco_f18",
    "idemia_sigma": "idemia_morphoaccess_sigma",
    "zk_speedface": "zkteco_speedface_v5l",
    "suprema_bs2": "suprema_biostation_2",
    "anviz_ep300": "anviz_ep300",
    "hik_generic": "hikvision_generic",
}

def get_terminal_model(model_key: str) -> Optional[TerminalModel]:
    """Récupère un modèle de terminal par clé"""
    if model_key in TERMINAL_SHORTCUTS:
        model_key = TERMINAL_SHORTCUTS[model_key]
    return TERMINAL_MODELS.get(model_key)

def list_all_models() -> Dict[str, dict]:
    """Liste tous les modèles disponibles"""
    return {
        key: model.to_dict()
        for key, model in TERMINAL_MODELS.items()
    }

def get_terminal_env_config(model_key: str) -> Dict[str, str]:
    """Génère la configuration .env pour un modèle"""
    model = get_terminal_model(model_key)
    if not model:
        raise ValueError(f"Modèle inconnu: {model_key}")
    return model.to_env_config()