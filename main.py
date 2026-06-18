import asyncio
import signal
import logging
from pointage_prodac.terminal_listener import TerminalSocketServer, TerminalDataParser
from pointage_prodac.pointage import PointageDispatcher
from pointage_prodac.logger_pointage import log_manager
from pointage_prodac.config_pointage import config
from pointage_prodac.models import init_db,get_task_session,Employe,gen_id
from contextlib import asynccontextmanager
from sqlmodel import select
logging.basicConfig(level=config.log.level)
logger = logging.getLogger(__name__)
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from pointage_prodac.logger_pointage import log_manager
from pointage_prodac.config_pointage import config
import asyncio  

from pointage_prodac.logger_pointage import log_manager
from pointage_prodac.config_pointage import config
from fastapi import FastAPI, HTTPException, Query
from typing import Optional, Dict, List
from pointage_prodac.terminal_model import (
    get_terminal_model,
    list_all_models,
    get_terminal_env_config,
)
from pointage_prodac.utils_planning import (
    suivi_mensuel_employe,
    suivi_semaine_employe,
    suivi_jour_tous_employes,
)
from datetime import date


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield



app = FastAPI(
    title="teste integration Pointeuse biometrique avec RH_manager",
    version="0.0.1",
    lifespan=lifespan,
)

""" # Peut etre difinit mais en local ferme pas necessaire
app.add_middleware(
    CORSMiddleware,
    allow_origins="0.0.0.0", ### definissez ici les reseau autorise a y acceder
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

"""
@app.websocket("/ws/pointages")
async def websocket_pointages(websocket: WebSocket):
    """Stream des pointages en temps réel"""
    await websocket.accept()
    
    try:
        while True:
            # Envoyer les événements toutes les 2 secondes
            events = log_manager.get_recent_events(limit=50)
            await websocket.send_json({
                "events": events,
                "config": {
                    "pause_mode": config.pause.mode,
                    "pointage_mode": config.pointage.mode_arrivee,
                },
            })
            await asyncio.sleep(2)
    except:
        pass

@app.get("/config")
async def get_config():
    """Retourne la config actuelle"""
    return {
        "terminal_format": config.terminal_data.format,
        "pause_mode": config.pause.mode,
        "pointage_rules": {
            "arrivee": config.pointage.mode_arrivee,
            "depart": config.pointage.mode_depart,
        },
        "logs": config.log.format,
        "network": {
            "host": config.network.host,
            "port": config.network.port,
        },
    }

@app.get("/")
async def dashboard():
    """Dashboard HTML simple"""
    return HTMLResponse("""
    <html>
    <head>
        <title>Suivi Pointages</title>
        <style>
            body { font-family: monospace; background: #1e1e1e; color: #0f0; padding: 20px; }
            .event { padding: 10px; border-bottom: 1px solid #333; }
            .action { font-weight: bold; }
            .warning { color: #ff6b6b; }
        </style>
    </head>
    <body>
        <h1> **************//Suivi Pointages//********</h1>
        <div id="events"></div>
        <script>
            const ws = new WebSocket('ws://localhost:8000/ws/pointages');
            ws.onmessage = (e) => {
                const {events} = JSON.parse(e.data);
                document.getElementById('events').innerHTML = events
                    .reverse()
                    .map(e => `
                        <div class="event">
                            <span class="action">${e.action}</span> 
                            ${e.employe_name} à ${e.heure}
                            ${e.warning ? `<span class="warning"> ⚠️ ${e.warning}</span>` : ''}
                        </div>
                    `).join('');
            };
        </script>
    </body>
    </html>
    """)

@app.get("/suivi/jour")
async def suivi_jour(date_str: str = None):
    """Vue journalière : tous les employés vs leur planning."""
    return await suivi_jour_tous_employes(date_str=date_str)

@app.get("/suivi/employe/{employe_id}/semaine")
async def suivi_semaine(employe_id: str, date_ref: str = None):
    """Suivi hebdomadaire d'un employé."""
    return await suivi_semaine_employe(
        employe_id=employe_id,
        date_ref=date_ref,
    )

@app.get("/suivi/employe/{employe_id}/mois")
async def suivi_mois(
    employe_id: str,
    annee: int = None,
    mois: int = None,
):
    """Suivi mensuel complet d'un employé avec détail jour par jour."""
    today = date.today()
    return await suivi_mensuel_employe(
        employe_id=employe_id,
        annee=annee or today.year,
        mois=mois or today.month,
    )



@app.get("/configurator/models")
async def list_terminal_models():
    """Liste tous les modèles de terminaux disponibles"""
    return {
        "total": len(list_all_models()),
        "models": list_all_models(),
    }

@app.get("/configurator/models/{model_key}")
async def get_model_details(model_key: str):
    """Récupère les détails d'un modèle spécifique"""
    model = get_terminal_model(model_key)
    if not model:
        raise HTTPException(status_code=404, detail=f"Modèle non trouvé: {model_key}")
    
    return {
        "model": model.to_dict(),
        "env_config": model.to_env_config(),
        "instructions": {
            "setup": _get_setup_instructions(model_key),
            "network": _get_network_instructions(model),
            "validation": _get_validation_instructions(model),
        }
    }

@app.get("/configurator/models/{model_key}/preview")
async def preview_configuration(model_key: str):
    """Preview la configuration générée sans sauvegarder"""
    model = get_terminal_model(model_key)
    if not model:
        raise HTTPException(status_code=404, detail=f"Modèle non trouvé: {model_key}")
    
    config = model.to_env_config()
    
    # Format .env
    env_content = "\n".join([f"{k}={v}" for k, v in config.items()])
    
    return {
        "model": model.name,
        "env_content": env_content,
        "example_data": model.example_data,
        "notes": model.notes,
        "url_doc": model.documentation_url,
    }

@app.post("/configurator/models/{model_key}/apply")
async def apply_configuration(
    model_key: str,
    override: Optional[Dict[str, str]] = None
):
    """Applique la configuration (sauvegarde .env)"""
    model = get_terminal_model(model_key)
    if not model:
        raise HTTPException(status_code=404, detail=f"Modèle non trouvé: {model_key}")
    
    config = model.to_env_config()
    
    # Override si fourni
    if override:
        config.update(override)
    
    # Sauvegarder dans .env
    import os
    env_path = ".env"
    
    try:
        with open(env_path, "w") as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        
        return {
            "status": "success",
            "message": f"Configuration appliquée pour {model.name}",
            "file": env_path,
            "config": config,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur écriture .env: {str(e)}")

@app.get("/configurator/search")
async def search_terminal(
    query: str = Query(..., min_length=2),
    manufacturer: Optional[str] = None,
):
    """Recherche un terminal par nom ou fabricant"""
    models = list_all_models()
    results = []
    
    q = query.lower()
    for key, model in models.items():
        if q in model["name"].lower() or q in model["manufacturer"].lower():
            if manufacturer and model["manufacturer"].lower() != manufacturer.lower():
                continue
            results.append({"key": key, **model})
    
    return {
        "query": query,
        "count": len(results),
        "results": results,
    }

@app.get("/configurator/by-manufacturer")
async def list_by_manufacturer():
    """Liste les terminaux groupés par fabricant"""
    models = list_all_models()
    by_manufacturer = {}
    
    for key, model in models.items():
        mfg = model["manufacturer"]
        if mfg not in by_manufacturer:
            by_manufacturer[mfg] = []
        by_manufacturer[mfg].append({"key": key, **model})
    
    return {
        "manufacturers": sorted(by_manufacturer.keys()),
        "by_manufacturer": by_manufacturer,
    }

@app.post("/configurator/test/{model_key}")
async def test_connection(
    model_key: str,
    host: Optional[str] = "localhost",
):
    """Test la connexion à un terminal (simulation)"""
    model = get_terminal_model(model_key)
    if not model:
        raise HTTPException(status_code=404, detail=f"Modèle non trouvé: {model_key}")
    
    import socket
    
    # Test de connexion simple
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, model.port))
    sock.close()
    
    connected = result == 0
    
    return {
        "model": model.name,
        "host": host,
        "port": model.port,
        "protocol": model.protocol,
        "connected": connected,
        "message": "Connexion réussie" if connected else f"Impossible de se connecter à {host}:{model.port}",
        "troubleshoot": _get_troubleshoot(model, connected),
    }



# ═══════════════════════════════════════════════════════════════════════
# ENREGISTREMENT EMPLOYÉS + SYNCHRONISATION ID_POINTEUSE
# ═══════════════════════════════════════════════════════════════════════

from fastapi import HTTPException
from pydantic import BaseModel
from typing import List

class EmployeRegistrationRequest(BaseModel):
    """Formulaire pour enregistrer un nouvel employé"""
    id_pointeuse: str  # ← Le seul lien vers la pointeuse
    prenom: str
    nom: str
    poste: str = ""
    departement: str = ""
    email: str = ""
    telephone: str = ""
    
    heure_arrivee_prevue: str = "08:00"
    heure_depart_prevue: str = "17:00"
    duree_pause_min: int = 60

class EmployeInDB(BaseModel):
    """Réponse employé enregistré"""
    id: str
    id_pointeuse: str
    nom: str
    prenom: str
    poste: str
    created_at: str


##### Vous pouvez ici overrite pour et enlever gen_id //pour creer des id manuellemet
@app.post("/admin/employes/enregistrer")
async def enregistrer_employe(data: EmployeRegistrationRequest):
    """
    Enregistre un nouvel employé en BD avec un ID de pointeuse.
    
    /// id_pointeuse doit exister sur la pointeuse physique//demareer le simulator si pas deja demarer avant de ttester sur le reseaxx DHCP votre leWSde votre terminal
    """
    
    # Vérifier unicité id_pointeuse
    async with get_task_session() as session:
        existing = await session.execute(
            select(Employe).where(Employe.id_pointeuse == data.id_pointeuse)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"ID pointeuse '{data.id_pointeuse}' déjà utilisé"
            )
    
    # Créer l'employé
    emp = Employe(
        id=gen_id(),
        id_pointeuse=data.id_pointeuse,  # ← LIEN CRITIQUE
        prenom=data.prenom,
        nom=data.nom,
        poste=data.poste,
        departement=data.departement,
        email=data.email,
        telephone=data.telephone,
        heure_arrivee_prevue=data.heure_arrivee_prevue,
        heure_depart_prevue=data.heure_depart_prevue,
        duree_pause_min=data.duree_pause_min,
        actif=1,
    )
    
    # Sauvegarder
    async with get_task_session() as session:
        session.add(emp)
        await session.commit()
        await session.refresh(emp)
    
    return {
        "ok": True,
        "message": f" {data.prenom} {data.nom} enregistré",
        "employe": {
            "id": emp.id,
            "id_pointeuse": emp.id_pointeuse,
            "nom": emp.nom,
            "prenom": emp.prenom,
            "poste": emp.poste,
            "created_at": emp.created_at,
        }
    }

@app.get("/admin/employes/liste")
async def lister_employes(actif_only: bool = True):
    """Liste tous les employés avec leur ID pointeuse"""
    async with get_task_session() as session:
        query = select(Employe).order_by(Employe.nom)
        if actif_only:
            query = query.where(Employe.actif == 1)
        
        result = await session.execute(query)
        employes = result.scalars().all()
    
    return {
        "total": len(employes),
        "employes": [
            {
                "id": e.id,
                "id_pointeuse": e.id_pointeuse,
                "nom": e.nom,
                "prenom": e.prenom,
                "poste": e.poste,
                "email": e.email,
                "actif": e.actif == 1,
            }
            for e in employes
        ]
    }

@app.get("/admin/employes/{employe_id}")
async def get_employe_details(employe_id: str):
    """Récupère les détails d'un employé"""
    async with get_task_session() as session:
        emp = await session.execute(
            select(Employe).where(Employe.id == employe_id)
        )
        emp = emp.scalar_one_or_none()
    
    if not emp:
        raise HTTPException(status_code=404, detail="Employé non trouvé")
    
    return {
        "id": emp.id,
        "id_pointeuse": emp.id_pointeuse,
        "nom": emp.nom,
        "prenom": emp.prenom,
        "poste": emp.poste,
        "departement": emp.departement,
        "email": emp.email,
        "telephone": emp.telephone,
        "heure_arrivee_prevue": emp.heure_arrivee_prevue,
        "heure_depart_prevue": emp.heure_depart_prevue,
        "duree_pause_min": emp.duree_pause_min,
        "actif": emp.actif == 1,
        "created_at": emp.created_at,
    }

@app.put("/admin/employes/{employe_id}")
async def modifier_employe(employe_id: str, data: EmployeRegistrationRequest):
    """Modifie un employé (sauf id_pointeuse une fois créé)"""
    async with get_task_session() as session:
        emp = await session.execute(
            select(Employe).where(Employe.id == employe_id)
        )
        emp = emp.scalar_one_or_none()
    
    if not emp:
        raise HTTPException(status_code=404, detail="Employé non trouvé")
    
    # Mise à jour
    emp.prenom = data.prenom
    emp.nom = data.nom
    emp.poste = data.poste
    emp.departement = data.departement
    emp.email = data.email
    emp.telephone = data.telephone
    emp.heure_arrivee_prevue = data.heure_arrivee_prevue
    emp.heure_depart_prevue = data.heure_depart_prevue
    emp.duree_pause_min = data.duree_pause_min
    
    async with get_task_session() as session:
        session.add(emp)
        await session.commit()
    
    return {
        "ok": True,
        "message": f"✓{data.prenom} {data.nom} modifié"
    }

@app.delete("/admin/employes/{employe_id}")
async def supprimer_employe(employe_id: str):
    """Désactive un employé (soft delete)"""
    async with get_task_session() as session:
        emp = await session.execute(
            select(Employe).where(Employe.id == employe_id)
        )
        emp = emp.scalar_one_or_none()
    
    if not emp:
        raise HTTPException(status_code=404, detail="Employé non trouvé")
    
    emp.actif = 0
    async with get_task_session() as session:
        session.add(emp)
        await session.commit()
    
    return {"ok": True, "message": f"✓ {emp.nom} désactivé"}

@app.get("/admin/sync-status")
async def sync_status():
    """État de synchronisation pointeuse ↔ DB"""
    async with get_task_session() as session:
        total = (await session.execute(
            select(Employe).where(Employe.actif == 1)
        )).scalars().all()
    
    with_id_ptr = [e for e in total if e.id_pointeuse and e.id_pointeuse.strip()]
    without_id_ptr = [e for e in total if not e.id_pointeuse or not e.id_pointeuse.strip()]
    
    return {
        "total_employes": len(total),
        "avec_id_pointeuse": len(with_id_ptr),
        "sans_id_pointeuse": len(without_id_ptr),
        "sync_ratio_pct": round((len(with_id_ptr) / len(total) * 100) if total else 0, 1),
        "employes_incomplets": [
            {
                "id": e.id,
                "nom": f"{e.prenom} {e.nom}",
                "id_pointeuse": e.id_pointeuse or "N/A",
            }
            for e in without_id_ptr
        ]
    }

@app.get("/admin")
async def admin_page():
    """Page d'administration des employés"""
    return HTMLResponse(ADMIN_HTML)


ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Enregistrement Employés</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2em; margin-bottom: 10px; }
        
        .content {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 30px;
            padding: 30px;
        }
        
        .card {
            background: #f9f9f9;
            border: 1px solid #eee;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        .card h2 {
            color: #667eea;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
            font-size: 14px;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 5px rgba(102, 126, 234, 0.3);
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
            width: 100%;
        }
        
        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn-danger {
            background: #ef4444;
            color: white;
            padding: 8px 16px;
            font-size: 12px;
        }
        
        .btn-danger:hover {
            background: #dc2626;
        }
        
        .status {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 15px;
            display: none;
        }
        
        .status.success {
            display: block;
            background: #d1fae5;
            color: #065f46;
            border-left: 4px solid #10b981;
        }
        
        .status.error {
            display: block;
            background: #fee2e2;
            color: #7f1d1d;
            border-left: 4px solid #ef4444;
        }
        
        .table-responsive {
            overflow-x: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        
        table th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
        }
        
        table td {
            padding: 12px;
            border-bottom: 1px solid #eee;
        }
        
        table tr:hover {
            background: #f5f5f5;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        
        .badge-success {
            background: #d1fae5;
            color: #065f46;
        }
        
        .badge-warning {
            background: #fef3c7;
            color: #92400e;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-card .value {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .stat-card .label {
            font-size: 12px;
            opacity: 0.9;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #999;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .required {
            color: #ef4444;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1> Administration Employés</h1>
            <p>Enregistrement et synchronisation avec pointeuse biométrique</p>
        </div>
        
        <div class="content">
            <!-- FORMULAIRE -->
            <div>
                <div class="card">
                    <h2>Nouvel Employé</h2>
                    <div class="status" id="form-status"></div>
                    
                    <form id="form-employe" onsubmit="enregistrerEmploye(event)">
                        <div class="form-group">
                            <label>ID Pointeuse <span class="required">*</span></label>
                            <input 
                                type="text" 
                                id="id_pointeuse" 
                                placeholder="EMP001"
                                required
                            >
                            <small style="color: #666;">ID inscrit dans la pointeuse physique</small>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Prénom <span class="required">*</span></label>
                                <input type="text" id="prenom" required>
                            </div>
                            <div class="form-group">
                                <label>Nom <span class="required">*</span></label>
                                <input type="text" id="nom" required>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Poste</label>
                            <input type="text" id="poste" placeholder="Développeur, Manager...">
                        </div>
                        
                        <div class="form-group">
                            <label>Département</label>
                            <input type="text" id="departement" placeholder="IT, RH...">
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Email</label>
                                <input type="email" id="email" placeholder="nom@exemple.com">
                            </div>
                            <div class="form-group">
                                <label>Téléphone</label>
                                <input type="tel" id="telephone">
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Horaire Arrivée</label>
                            <input type="time" id="heure_arrivee_prevue" value="08:00">
                        </div>
                        
                        <div class="form-group">
                            <label>Horaire Départ</label>
                            <input type="time" id="heure_depart_prevue" value="17:00">
                        </div>
                        
                        <div class="form-group">
                            <label>Durée Pause (min)</label>
                            <input type="number" id="duree_pause_min" value="60" min="30" max="180">
                        </div>
                        
                        <button type="submit" class="btn-primary">✓ Enregistrer Employé</button>
                    </form>
                </div>
                
                <div class="card">
                    <h2>ℹ Utilisation</h2>
                    <ol style="padding-left: 20px; color: #666; font-size: 14px; line-height: 1.8;">
                        <li>Créer l'employé avec son <strong>ID pointeuse</strong> (ex: EMP001)</li>
                        <li>L'ID doit correspondre à celui enregistré sur la pointeuse physique</li>
                        <li>Cet ID est le seul lien entre terminal et base de données</li>
                        <li>Ensuite, lancer la simulation ou connecter la vraie pointeuse</li>
                    </ol>
                </div>
            </div>
            
            <!-- LISTE EMPLOYÉS -->
            <div>
                <div class="card">
                    <h2> État de Synchronisation</h2>
                    <div id="sync-status" class="loading">
                        <div class="spinner"></div>
                        Chargement...
                    </div>
                </div>
                
                <div class="card">
                    <h2> Employés Enregistrés</h2>
                    <div id="employes-list" class="loading">
                        <div class="spinner"></div>
                        Chargement...
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Enregistrer employé
        async function enregistrerEmploye(e) {
            e.preventDefault();
            
            const data = {
                id_pointeuse: document.getElementById("id_pointeuse").value.trim(),
                prenom: document.getElementById("prenom").value.trim(),
                nom: document.getElementById("nom").value.trim(),
                poste: document.getElementById("poste").value.trim(),
                departement: document.getElementById("departement").value.trim(),
                email: document.getElementById("email").value.trim(),
                telephone: document.getElementById("telephone").value.trim(),
                heure_arrivee_prevue: document.getElementById("heure_arrivee_prevue").value,
                heure_depart_prevue: document.getElementById("heure_depart_prevue").value,
                duree_pause_min: parseInt(document.getElementById("duree_pause_min").value),
            };
            
            try {
                const res = await fetch("/admin/employes/enregistrer", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });
                
                const result = await res.json();
                
                if (!res.ok) {
                    showStatus("error", result.detail || "Erreur");
                    return;
                }
                
                showStatus("success", result.message);
                document.getElementById("form-employe").reset();
                
                // Recharger la liste
                setTimeout(() => {
                    loadEmployesList();
                    loadSyncStatus();
                }, 1000);
                
            } catch (err) {
                showStatus("error", err.message);
            }
        }
        
        function showStatus(type, msg) {
            const el = document.getElementById("form-status");
            el.textContent = msg;
            el.className = `status ${type}`;
        }
        
        // Charger la liste d'employés
        async function loadEmployesList() {
            try {
                const res = await fetch("/admin/employes/liste");
                const data = await res.json();
                
                const html = `
                    <table>
                        <thead>
                            <tr>
                                <th>Nom</th>
                                <th>ID Pointeuse</th>
                                <th>Poste</th>
                                <th>Email</th>
                                <th>Statut</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.employes.map(e => `
                                <tr>
                                    <td><strong>${e.prenom} ${e.nom}</strong></td>
                                    <td><code>${e.id_pointeuse}</code></td>
                                    <td>${e.poste || "-"}</td>
                                    <td>${e.email || "-"}</td>
                                    <td>
                                        <span class="badge ${e.actif ? 'badge-success' : 'badge-warning'}">
                                            ${e.actif ? 'Actif' : 'Inactif'}
                                        </span>
                                    </td>
                                    <td>
                                        <button class="btn-danger" onclick="supprimerEmploye('${e.id}')">
                                            Supprimer
                                        </button>
                                    </td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                `;
                
                document.getElementById("employes-list").innerHTML = html;
                
            } catch (err) {
                document.getElementById("employes-list").innerHTML = `<p style="color: red;">Erreur: ${err.message}</p>`;
            }
        }
        
        // Charger l'état de sync
        async function loadSyncStatus() {
            try {
                const res = await fetch("/admin/sync-status");
                const data = await res.json();
                
                const html = `
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="label">Total Employés</div>
                            <div class="value">${data.total_employes}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Avec ID Pointeuse</div>
                            <div class="value">${data.avec_id_pointeuse}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Taux Sync</div>
                            <div class="value">${data.sync_ratio_pct}%</div>
                        </div>
                    </div>
                `;
                
                if (data.employes_incomplets.length > 0) {
                    html += `
                        <p style="color: #666; font-size: 12px; margin-top: 10px;">
                            <strong>${data.employes_incomplets.length} employé(s) sans ID pointeuse:</strong>
                        </p>
                        <ul style="font-size: 12px; color: #666; margin-left: 20px;">
                            ${data.employes_incomplets.map(e => `
                                <li>${e.nom}</li>
                            `).join("")}
                        </ul>
                    `;
                } else {
                    html += `<p style="color: #10b981; margin-top: 10px;">✓ Tous les employés sont synchronisés!</p>`;
                }
                
                document.getElementById("sync-status").innerHTML = html;
                
            } catch (err) {
                document.getElementById("sync-status").innerHTML = `<p style="color: red;">Erreur: ${err.message}</p>`;
            }
        }
        
        // Supprimer employé
        async function supprimerEmploye(id) {
            if (!confirm("Êtes-vous sûr de vouloir désactiver cet employé?")) return;
            
            try {
                const res = await fetch(`/admin/employes/${id}`, { method: "DELETE" });
                if (res.ok) {
                    loadEmployesList();
                    loadSyncStatus();
                }
            } catch (err) {
                alert("Erreur: " + err.message);
            }
        }
        
        // Charger au démarrage
        window.addEventListener("load", () => {
            loadEmployesList();
            loadSyncStatus();
        });
    </script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _get_setup_instructions(model_key: str) -> Dict[str, str]:
    """Instructions de setup par modèle"""
    instructions = {
        "zkteco_k14": """
1. Connecter le terminal au réseau via Ethernet
2. Accéder à l'interface web: http://[IP_TERMINAL]:8080
3. Admin / 123456
4. Configurer FTP ou Telnet pour export
5. Télécharger la liste des empreintes
6. Configurer pointage vers 0.0.0.0:9999
        """,
        "hikvision_ds_k1a8503ef": """
1. Initialiser le terminal (bouton Power)
2. Accéder à http://[IP_TERMINAL]:8080
3. Inscrire les empreintes digitales
4. Configurer API REST
5. Configurer webhooks vers http://[NOTRE_SERVEUR]:8000/webhook
        """,
        "zkteco_speedface_v5l": """
1. Brancher et attendre boot (30 sec)
2. Accéder à http://[IP_TERMINAL]:8888
3. Configuration réseau (DHCP ou statique)
4. Calibrer caméra
5. Test reconnaissance (reconnaissance en <1 sec)
6. Activer API REST
        """,
    }
    return instructions.get(model_key, "Voir documentation fabricant")

def _get_network_instructions(model) -> Dict[str, str]:
    """Instructions réseau par type de protocole"""
    if "Telnet" in model.protocol:
        return {
            "connection": f"telnet [IP] {model.port}",
            "default_password": "Voir documentation",
            "commands": "Consulter manuel Telnet",
        }
    elif "HTTP" in model.protocol:
        return {
            "connection": f"http://[IP]:{model.port}",
            "authentication": "Basic Auth ou OAuth2",
            "default_credentials": "admin/123456 (à changer)",
        }
    elif "Modbus" in model.protocol:
        return {
            "connection": f"Modbus TCP port {model.port}",
            "coils": "Consulter adressage Modbus",
            "holding_registers": "Consulter registres",
        }
    return {}

def _get_validation_instructions(model) -> Dict[str, str]:
    """Instructions pour valider la connexion"""
    return {
        "step_1": f"Vérifier connectivité: ping [IP_TERMINAL]",
        "step_2": f"Vérifier port: telnet [IP_TERMINAL] {model.port}",
        "step_3": f"Format attendu: {model.data_format.value}",
        "step_4": "Envoyer un badge de test",
        "step_5": "Vérifier logs: tail -f logs/pointage.log",
    }

def _get_troubleshoot(model, connected: bool) -> Dict[str, str]:
    if connected:
        return {
            "status": "OK",
            "next_steps": ["Vérifier authentification", "Tester envoi de données"],
        }
    return {
        "status": "ERREUR",
        "checklist": [
            f"Terminal à l'adresse correcte?",
            f"Port {model.port} accessible?",
            f"Firewall bloque?",
            f"Terminal actif et en réseau?",
            f"IP correcte dans le formulaire?",
        ]
    }

class TerminalServerApp:
    
    def __init__(self):
        self.dispatcher = PointageDispatcher()
        self.server = TerminalSocketServer(
            host=config.network.host,
            port=config.network.port,
            on_pointage_event=self.handle_pointage,
        )
        self._running = False
    
    async def handle_pointage(self, event):
        """Callback du server → dispatcher"""
        result = await self.dispatcher.handle_terminal_event(event)
        
        if not result.get("ok"):
            logger.error(f"Erreur pointage: {result.get('error')}")


    async def start(self):
        print("=" * 60)
        print(f"  SERVER POINTAGE")
        print(f"  Host: {config.network.host}:{config.network.port}")
        print(f"  Format terminal: {config.terminal_data.format.upper()}")
        print(f"  Mode pause: {config.pause.mode.upper()}")
        print(f"  Mode pointage (arrivée): {config.pointage.mode_arrivee}")
        print(f"  Logs: {config.log.format} → {config.log.output}")
        print("=" * 60)
        
        logger.info("Base de donnees initialisee")
        
        self._running = True
        await self.server.start()
        
        # Gestion du signal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


    async def stop(self):
        """Arrête le serveur proprement"""
        if self._running:
            self._running = False
            print("\n *****$$$****Arrêt du serveur...")
            await self.server.stop()
            logger.info("Server arrêté")


# Route de santé
@app.get("/health", tags=["système"])
async def health_check():
    return {"status": "ok", "version": app.version}



if __name__ == "__main__":
    app = TerminalServerApp()
    asyncio.run(app.start())