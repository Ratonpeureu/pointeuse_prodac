# SYSTÈME DE POINTAGE - DOCUMENTATION COMPLÈTE

## TABLE DES MATIÈRES
1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Architecture](#architecture)
4. [API REST](#api-rest)
5. [Scénarios de Test](#scénarios-de-test)
6. [Troubleshooting](#troubleshooting)

---

## INSTALLATION

### Prérequis
- Python 3.9+
- pip
- virtualenv (recommandé)

### Setup (Linux)
```bash
# 1. Cloner/naviguer
cd pointage_prodac

# 2. Virtual env
python3 -m venv venv
source venv/bin/activate

# 3. Installer dépendances
pip install -r requirements.txt

# 4. Copier config
cp env.example .env

# 5. Créer logs
mkdir -p logs

# 6. Lancer
python -m main &
uvicorn api:app --reload --port 8000 &
```

### Setup (Windows - PowerShell Admin)
```powershell
# 1. Virtual env
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Installer dépendances
pip install -r requirements.txt

# 3. Copier config
Copy-Item env.example .env

# 4. Créer logs
mkdir -p logs -ErrorAction SilentlyContinue

# 5. Lancer (deux windows séparées)
# Terminal 1:
python -m main

# Terminal 2:
uvicorn api:app --reload --port 8000
```

### requirements.txt
fastapi==0.104.1

uvicorn==0.24.0

sqlmodel==0.0.14

sqlalchemy==2.0.23

aiosqlite==0.19.0

python-dotenv==1.0.0
httpx
httpx_ws
Can not remove version fixed
---

## CONFIGURATION

### Hiérarchie des configurations

Valeurs en dur dans config_pointage.py (defaults)

↓
Variables d'environnement (fichier .env)

↓
Résultat final = utilisé par le système


### Paramètres critiques

| Paramètre | Valeurs | Défaut | Impact |
|-----------|---------|--------|--------|
| TERMINAL_FORMAT | csv, json, binary | csv | Comment parser les données |
| PAUSE_MODE | terminal, system, hybrid | terminal | Qui gère les pauses |
| POINTAGE_ARRIVEE_MODE | first_only, last_only | first_only | 1er arrivée ou dernier badge |
| LOG_LEVEL | DEBUG, INFO, WARNING, ERROR | INFO | Verbosité des logs |
| TERMINAL_PORT | 1-65535 | 9999 | Port d'écoute |

### Cas de configuration par type de pointeuse

#### Cas 1: Pointeuse envoie CSV simple
```env
TERMINAL_FORMAT=csv
TERMINAL_DELIMITER=,
TERMINAL_TIMESTAMP_FORMAT=%Y-%m-%d %H:%M:%S
# Données: "12345,2026-06-18 08:30:15,0,1,0,0"
```

#### Cas 2: Pointeuse envoie JSON
```env
TERMINAL_FORMAT=json
# Données: {"id_pointeuse": "12345", "timestamp": "2026-06-18T08:30:15", "action": 0}
```

#### Cas 3: Pointeuse envoie CSV avec ordre custom
```env
TERMINAL_FORMAT=csv
TERMINAL_DELIMITER=;
TERMINAL_FIELD_MAPPING={"timestamp": 0, "id_pointeuse": 1, "action": 2, "statut_badge": 3}
# Données: "2026-06-18 08:30:15;12345;0;1;extra"
```

#### Cas 4: Pointeuse gère les pauses
```env
PAUSE_MODE=terminal
# Envoie: action 0=arrivée, 1=pause, 2=fin_pause, 3=départ
```

#### Cas 5: Système calcule les pauses (1er arrivée + dernier départ)
```env
PAUSE_MODE=system
# Envoie seulement: action 0=arrivée, 3=départ (ignorer 1 et 2)
PAUSE_DEFAULT_MIN=60
```

---

## ARCHITECTURE

### Flux de données
Terminal Physique

↓

[Socket 9999]

↓

TerminalSocketServer (écoute)

↓

TerminalDataParser (parse CSV/JSON)

↓

PointageEvent (objet normalisé)

↓

PointageDispatcher (logique métier)

├─ Vérifie re-badgeages

├─ Gère pauses (terminal vs système)

├─ Calcule retards

└─ Sauvegarde en DB

↓

Pointage (table DB)

↓

log_manager (console + fichier)

↓

WebSocket (dashboard temps réel)

### Classes principales

#### TerminalDataParser
```python
# Parse n'importe quel format vers PointageEvent
PointageEvent = TerminalDataParser.parse(raw_data)
# Sortie normalisée:
# - id_pointeuse: str
# - timestamp: datetime
# - action: int (0=arrivée, 1=pause, 2=fin_pause, 3=départ)
# - action_name: str
# - received_at: datetime
```

#### PointageDispatcher
```python
# Traite l'événement avec règles de config
result = await dispatcher.handle_terminal_event(event)
# Retourne:
# {
#   "ok": bool,
#   "statut": "travail" | "pause" | "off",
#   "heure": "HH:MM",
#   "action": "Arrivée" | "Pause" | "Fin pause" | "Départ",
#   "message": "✓ Arrivée à 08:30",
#   "warning": None | "Pause déviée de +15 min",
#   "ignored": False | True
# }
```

#### Pointage (SQLModel)
```python
# Enregistrement en base
{
  "id": "uuid",
  "employe_id": "emp123",
  "date_jour": "2026-06-18",
  "heure_arrivee": "08:30",
  "heure_pause": "13:00",
  "heure_fin_pause": "14:00",
  "heure_depart": "17:30",
  "statut": "off",
  "retard_arrivee_min": 0,
  ...
}
```

---

## API REST

### URL de base
http://localhost:8000

### WebSocket (temps réel)
ws://localhost:8000/ws/pointages

### Endpoints

#### GET /
Dashboard HTML interactif avec les 50 derniers pointages

**Réponse:** HTML
```html
<h1>Suivi Pointages</h1>
<div id="events">
  <div class="event">
    <span class="action">Arrivée</span> 
    Prodac à 08:30
  </div>
  ...
</div>
```

---

#### GET /config
Configuration actuelle du système

**Réponse:**
```json
{
  "terminal_format": "csv",
  "pause_mode": "terminal",
  "pointage_rules": {
    "arrivee": "first_only",
    "depart": "last_only"
  },
  "logs": "structured",
  "network": {
    "host": "0.0.0.0",
    "port": 9999
  }
}
```

---

#### WS /ws/pointages
Stream WebSocket des pointages en temps réel

**Message toutes les 2 secondes:**
```json
{
  "events": [
    {
      "timestamp": "2026-06-18T08:30:15.123456",
      "employe_id": "emp123",
      "employe_name": "Banta",
      "action": "Arrivée",
      "heure": "08:30",
      "statut": "travail",
      "message": "✓ Arrivée à 08:30",
      "warning": null
    },
    {
      "timestamp": "2026-06-18T13:00:05.654321",
      "employe_id": "emp456",
      "employe_name": "Fatou",
      "action": "Pause",
      "heure": "13:00",
      "statut": "pause",
      "message": "⏸ Pause à 13:00",
      "warning": null
    }
  ],
  "config": {
    "pause_mode": "terminal",
    "pointage_mode": "first_only"
  }
}
```

---

#### GET /suivi/jour
Vue journalière : tous les employés vs planning

**Query:**
?date_str=2026-06-18  (optionnel, défaut: aujourd'hui)

**Réponse:**
```json
{
  "date": "2026-06-18",
  "jour": "mercredi",
  "total": 25,
  "presents": 20,
  "absents": 3,
  "off_planning": 2,
  "employes": [
    {
      "employe_id": "emp123",
      "matricule": "EMP12345",
      "nom": "Banta",
      "prenom": "Dev",
      "poste": "Développeur",
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:30",
      "heure_depart": null,
      "retard_min": 30
    },
    {
      "employe_id": "emp456",
      "matricule": "EMP45600",
      "nom": "Fatou",
      "prenom": "Man",
      "poste": "Manager",
      "statut": "absent",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": null,
      "heure_depart": null,
      "retard_min": 0
    },
    {
      "employe_id": "emp789",
      "matricule": "EMP78900",
      "nom": "Gora",
      "prenom": "Sow",
      "poste": "Support",
      "statut": "off_planning",
      "prevu_debut": "OFF",
      "prevu_fin": "OFF",
      "heure_arrivee": null,
      "heure_depart": null,
      "retard_min": 0
    }
  ]
}
```

---

#### GET /suivi/employe/{employe_id}/semaine
Suivi hebdomadaire d'un employé

**Query:**
?date_ref=2026-06-18  (optionnel, défaut: cette semaine)

**Réponse:**
```json
{
  "employe_id": "emp123",
  "nom": "Banta Dev",
  "semaine_du": "2026-06-16",
  "semaine_au": "2026-06-22",
  "source_planning": "mensuel",
  "jours_presents": 5,
  "jours_absents": 0,
  "details": [
    {
      "date": "2026-06-16",
      "jour": "lundi",
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:25",
      "heure_depart": "17:15",
      "retard_min": 25,
      "heures_travaillees": 8.83
    },
    {
      "date": "2026-06-17",
      "jour": "mardi",
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:00",
      "heure_depart": "17:00",
      "retard_min": 0,
      "heures_travaillees": 9.0
    },
    {
      "date": "2026-06-18",
      "jour": "mercredi",
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:30",
      "heure_depart": null,
      "retard_min": 30,
      "heures_travaillees": 0
    },
    {
      "date": "2026-06-19",
      "jour": "jeudi",
      "statut": "futur",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": null,
      "heure_depart": null
    },
    {
      "date": "2026-06-20",
      "jour": "vendredi",
      "statut": "futur",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": null,
      "heure_depart": null
    },
    {
      "date": "2026-06-21",
      "jour": "samedi",
      "statut": "off_planning",
      "prevu_debut": "OFF",
      "prevu_fin": "OFF"
    },
    {
      "date": "2026-06-22",
      "jour": "dimanche",
      "statut": "off_planning",
      "prevu_debut": "OFF",
      "prevu_fin": "OFF"
    }
  ]
}
```

---

#### GET /suivi/employe/{employe_id}/mois
Suivi mensuel complet d'un employé

**Query:**
?annee=2026&mois=6  (optionnel, défaut: mois courant)

**Réponse:**
```json
{
  "employe_id": "emp123",
  "nom": "Banta dev",
  "poste": "Développeur",
  "annee": 2026,
  "mois": 6,
  "source_planning": "mensuel",
  "jours_prevus": 22,
  "jours_presents": 21,
  "jours_absents": 1,
  "jours_off_planning": 8,
  "taux_presence_pct": 95.5,
  "total_retard_min": 180,
  "details": [
    {
      "date": "2026-06-01",
      "jour": "lundi",
      "prevu": true,
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:15",
      "heure_depart": "17:30",
      "retard_min": 15,
      "heures_travaillees": 9.25,
      "heures_sup": 1.0,
      "note": ""
    },
    {
      "date": "2026-06-02",
      "jour": "mardi",
      "prevu": true,
      "statut": "travail",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": "08:00",
      "heure_depart": "17:00",
      "retard_min": 0,
      "heures_travaillees": 9.0,
      "heures_sup": 0.0,
      "note": ""
    },
    {
      "date": "2026-06-03",
      "jour": "mercredi",
      "prevu": true,
      "statut": "absent",
      "prevu_debut": "08:00",
      "prevu_fin": "17:00",
      "heure_arrivee": null,
      "heure_depart": null,
      "retard_min": 0,
      "note": "Absence non justifiée"
    },
    {
      "date": "2026-06-07",
      "jour": "dimanche",
      "prevu": false,
      "statut": "off_planning",
      "heure_arrivee": null,
      "heure_depart": null,
      "retard_min": 0,
      "note": "Jour non travaillé selon planning"
    }
  ]
}
```

---

## SCÉNARIOS DE TEST

### Scénario 1: Test basique (mode système)

**Configuration:**
```env
TERMINAL_FORMAT=csv
PAUSE_MODE=system
POINTAGE_ARRIVEE_MODE=first_only
LOG_LEVEL=DEBUG
```

**Données envoyées au port 9999:**
Première arrivée (08:30):

12345,2026-06-18 08:30:15,0,1,0,0
Premier départ (17:30):

12345,2026-06-18 17:30:45,3,1,0,0

**Résultat attendu:**
```json
{
  "employe_id": "emp123",
  "date_jour": "2026-06-18",
  "heure_arrivee": "08:30",
  "heure_depart": "17:30",
  "statut": "off",
  "retard_arrivee_min": 30
}
```

**Dashboard:**
[08:30:15] Arrivée → 08:30 | Retard de 30 min

[17:30:45] Départ → 17:30 | À l'heure

---

### Scénario 2: Re-badgeage ignoré

**Configuration:**
```env
POINTAGE_ARRIVEE_MODE=first_only
REBADGE_IGNORE_MIN=5
```

**Données:**
08:30:15 - 1er badge (accepté)

08:31:00 - 2e badge (ignoré, <5 min)

08:36:00 - 3e badge (ignoré, >5 min mais déjà enregistré)

**Résultat:**
- 1er badge: "✓ Arrivée à 08:30" ✓
- 2e badge: "Re-badage ignoré (même jour)"
- 3e badge: "Re-badage ignoré (même jour)" 

---

### Scénario 3: Pauses terminales

**Configuration:**
```env
PAUSE_MODE=terminal
PAUSE_DEFAULT_MIN=60
PAUSE_WARN_OVER_MIN=15
```

**Données:**
08:30 - arrivée

13:00 - pause

14:15 - fin_pause (15 min supplémentaire)

17:30 - départ

**Résultat:**
```json
{
  "heure_arrivee": "08:30",
  "heure_pause": "13:00",
  "heure_fin_pause": "14:15",
  "heure_depart": "17:30"
}
```

**Dashboard:**
[08:30] Arrivée → À l'heure

[13:00] Pause → Pause à 13:00

[14:15] Fin pause → AVERTISSEMENT: Pause déviée de +15 min

[17:30] Départ → À l'heure

---

### Scénario 4: Absence (pas de pointage)

**Configuration:**
```env
(par défaut)
```

**Données:**
(aucune pour l'employé X le 2026-06-18)

**Résultat API /suivi/jour:**
```json
{
  "employe_id": "emp789",
  "nom": "Fatou Man",
  "statut": "absent",
  "heure_arrivee": null,
  "heure_depart": null,
  "retard_min": 0
}
```

---

### Scénario 5: Format JSON custom

**Configuration:**
```env
TERMINAL_FORMAT=json
TERMINAL_TIMESTAMP_FORMAT=%Y-%m-%dT%H:%M:%S
```

**Données:**
```json
{
  "id_pointeuse": "12345",
  "timestamp": "2026-06-18T08:30:15",
  "action": 0,
  "statut_badge": 1,
  "device_id": "DEVICE_A",
  "temperature": 36.5
}
```

**Résultat:** Parsé correctement, extra_data stocké

---

### Scénario 6: Planning mensuel vs employé

**Données employé (défaut):**
Arrivée: 08:00

Départ: 17:00

Pause: 13:00-14:00

**Pointage:**
08:30 (retard 30 min vs planning employé)

17:30 (30 min de départ)

**Résultat /suivi/jour:**
Source planning: "employe"

Heure prévue: "08:00" (depuis Employe.heure_arrivee_prevue)

Retard: 30 min

---

## TROUBLESHOOTING

### Problème: "Port 9999 already in use"

**Linux:**
```bash
# Trouver processus
lsof -i :9999

# Tuer le processus
kill -9 <PID>

# Ou utiliser autre port
export TERMINAL_PORT=10000
```

**Windows:**
```powershell
# Trouver processus
netstat -ano | findstr :9999

# Tuer le processus
taskkill /PID <PID> /F

# Ou modifier .env
TERMINAL_PORT=10000
```

---

### Problème: "Permission denied" sur ./logs

**Linux:**
```bash
mkdir -p logs
chmod 755 logs
chmod 644 logs/pointage.log ///fichier de log peut varies d'emplacement selon si c'est windows ou Mac
```

---

### Problème: "Employe non trouvé"

**Cause:** id_pointeuse n'existe pas en base

**Solution:**
```sql
-- Insérer un employé de test
INSERT INTO employe (id, id_pointeuse, prenom, nom, actif)
VALUES ('emp123', '12345', 'Banta', 'Dev', 1);
```

---

### Problème: Logs vides / Dashboard vide

**Vérifier:**
1. Le serveur socket écoute: `netstat -tuln | grep 9999`
2. Les données arrivent: `LOG_LEVEL=DEBUG` dans .env
3. La base existe: `ls ~/.local/share/tes_pointeuse/`
4. FastAPI lancé: `curl http://localhost:8000/config`

---

### Problème: Format CSV non parsé

**Vérifier:**
1. `TERMINAL_DELIMITER` correct (habituellement `,`)
2. Nombre de champs >= 6 (ou mapping custom)
3. Timestamp format correct (`TERMINAL_TIMESTAMP_FORMAT`)

**Test:**
```bash
# Envoyer manuellement
echo "12345,2026-06-18 08:30:15,0,1,0,0" | nc localhost 9999
```

---

### Problème: Configuration ne se met à jour pas

**Solution:**
1. Relancer le serveur: `Ctrl+C` puis `python -m main`
2. FastAPI: arrêter avec `Ctrl+C`
3. Vérifier syntaxe .env (pas d'espaces autour de `=`)

---

## LOGS

### Format Structured (JSON)

```json
{
  "timestamp": "2026-06-18T08:30:15.123456",
  "level": "INFO",
  "logger": "pointage",
  "message": "[Banta Dev] Arrivée → 08:30 | Retard de 30 min",
  "employe_id": "emp123",
  "action": "Arrivée"
}
```

### Format Simple (texte)
2026-06-18 08:30:15 - pointage - INFO - [Jean Dupont] Arrivée → 08:30 | Retard de 30 min

### Consulter les logs

```bash
# Temps réel
tail -f logs/pointage.log

# Avec jq (JSON pretty)
tail -f logs/pointage.log | jq .

# Filtrer par employé
grep "Banta" logs/pointage.log

# Dernières 50 lignes
tail -50 logs/pointage.log
```

---

## MÉTRIQUES

### Calculs effectués

| Métrique | Formule | Exemple |
|----------|---------|---------|
| Retard arrivée | heure_réelle - heure_prévue | 08:30 - 08:00 = 30 min |
| Retard départ | heure_réelle - heure_prévue | 17:30 - 17:00 = 30 min |
| Déviation pause | durée_réelle - durée_prévue | 75 min - 60 min = +15 min |
| Heures travaillées | départ - arrivée - pause | 17:30 - 08:30 - 60 min = 8.5h |
| Heures sup | max(0, heures_travaillées - 8) | 8.5h - 8h = 0.5h (ignoré, <1h) |
| Taux présence | jours_présents / jours_prévus * 100 | 21/22 * 100 = 95.5% |

---

## SAUVEGARDE/RESTAURATION

### Sauvegarde (Linux)
```bash
cp ~/.local/share/tes_pointeuse/test_pointeuse.db backup.db
```

### Restauration
```bash
cp backup.db ~/.local/share/tes_pointeuse/test_pointeuse.db
```

## Simpe fichier Sql db //pour le teste pas need to create contenaire Postgres //simple file db 

### Réinitialiser la base
```bash
rm ~/.local/share/tes_pointeuse/test_pointeuse.db
# La base se recréera automatiquement au démarrage
```

---

## Simulator pointeuse /file terminal_simulator.py

    Étape 1: Créer les employés en BD
    bash# Aller sur http://localhost:8000/admin
    # Formulaire préfill:

    EMP001 - Mohamed Diallo (08:00 - 17:00)
    EMP002 - Fatou Ndiaye (08:30 - 17:30)
    EMP003 - Amadou Cisse (07:45 - 16:45)
    Étape 2: Vérifier la synchronisation
    bashcurl http://localhost:8000/admin/sync-status

    # Doit retourner:
    {
      "total_employes": 3,
      "avec_id_pointeuse": 3,
      "sync_ratio_pct": 100.0,
      "employes_incomplets": []
    }
    Étape 3: Lancer la simulation
    bash# Terminal 1 - Serveur pointage
    python -m pointage_prodac.main

    # Terminal 2 - API
    uvicorn pointage_prodac.api:app --reload --port 8000

    # Terminal 3 - Simulateur
    python -m pointage_prodac.terminal_simulator
    Étape 4: Observer les pointages
    bash# Dashboard en temps réel
    http://localhost:8000/

    # Suivi journée
    curl http://localhost:8000/suivi/jour

    # Suivi employé/mois
    curl http://localhost:8000/suivi/employe/[ID]/mois?annee=2026&mois=6

    FLUX CRITIQUE ID_POINTEUSE
    ┌─────────────────────────────────────────────────────────┐
    │ SYNCHRONISATION ID_POINTEUSE ↔ EMPLOYE_ID              │
    └─────────────────────────────────────────────────────────┘

    ENREGISTREMENT (Admin)
        ├─ Créer employe en BD avec id_pointeuse = "EMP001"
        └─ ✓ id_pointeuse UNIQUE dans la table

    ARRIVÉE DU POINTAGE (Terminal)
        ├─ Pointeuse envoie: "EMP001,2026-06-18 08:30:15,0,0,K14"
        └─ TerminalDataParser extrait id_pointeuse = "EMP001"

    RECHERCHE EMPLOYE (PointageDispatcher)
        ├─ SELECT Employe WHERE id_pointeuse = "EMP001"
        └─ ✓ Trouve Mohamed Diallo (employe.id)

    SAUVEGARDE POINTAGE
        ├─ INSERT Pointage (employe_id, date_jour, heure_arrivee...)
        └─ ✓ Pointage liée au bon employé

    LIEN = id_pointeuse (UNIQUE, NON MODIFIABLE)