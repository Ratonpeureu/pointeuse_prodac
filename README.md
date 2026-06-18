# Système de Pointage Terminal - Documentation Complète
## Test
![Tests](https://github.com/USER/REPO/actions/workflows/tests.yml/badge.svg)
## Présentation

Système complet de pointage pour terminals de pointeuses physiques. Gère l'arrivée, pauses, départs et produit des rapports détaillés de présence par employé.

**Fonctionnalités:**
- Réception de données multi-format (CSV, JSON)
- Gestion flexible des pauses (terminal ou système)
- Règles configurables (re-badgeages, retards, etc.)
- Dashboard temps réel WebSocket
- API REST complète
- Suivi mensuel/hebdomadaire/journalier
- Logs structurés (JSON) ou simples

**Support:**
- Linux (recommandé)
- Windows
- macOS

---

## Installation rapide (5 min)

### Linux
```bash
# 1. Cloner
git clone pointeuse_prodac
cd pointeuse_prodac

# 2. Env
python3 -m venv venv && source venv/bin/activate

# 3. Deps
pip install -r requirements.txt

# 4. Config
cp env.example .env

# 5. Logs
mkdir -p logs

# 6. Run (Terminal 1)
python -m main

# 7. Run (Terminal 2)
uvicorn api:app --reload --port 8000

# 8. Accès
Ouvrir http://localhost:8000
```

### Windows (PowerShell Admin)
```powershell
git clone pointeuse_prodac
cd pointeuse_prodac
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy env.example .env
mkdir logs
# Terminal 1:
python -m main
# Terminal 2:
uvicorn api:app --reload --port 8000
```

---

## Configuration essentielle

### .env minimal

```env
# Format de la pointeuse
TERMINAL_FORMAT=csv                          # csv, json, ou binary
TERMINAL_DELIMITER=,

# Gestion des pauses
PAUSE_MODE=terminal                          # terminal, system, ou hybrid

# Règles de pointage
POINTAGE_ARRIVEE_MODE=first_only             # first_only ou last_only
POINTAGE_DEPART_MODE=last_only

# Réseau
TERMINAL_HOST=0.0.0.0
TERMINAL_PORT=9999

# Logs
LOG_LEVEL=INFO                               # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=structured                        # structured ou simple
LOG_OUTPUT=both                              # console, file, ou both
```

**Voir `env.example` pour documentation complète.**

---
## Architecture
┌─────────────────────────────────────────────────────────────┐

│                    TERMINAL PHYSIQUE                        │

│              (Pointeuse biométrique/RFID)                   │

└──────────────────────┬──────────────────────────────────────┘

│ CSV/JSON via TCP

↓

┌──────────────────────────────────────────────────────────────┐

│              SERVEUR POINTAGE (Port 9999)                    │

│                                                              │

│  1. TerminalSocketServer ← reçoit les données              │

│     ↓                                                        │

│  2. TerminalDataParser ← parse (CSV/JSON/Binary)           │

│     ↓                                                        │

│  3. PointageEvent ← normalisation                          │

│     ↓                                                        │

│  4. PointageDispatcher ← logique métier                    │

│     • Vérifie re-badgeages (first_only/last_only)          │

│     • Gère pauses (terminal/system/hybrid)                 │

│     • Calcule retards vs planning                          │

│     ↓                                                        │

│  5. Pointage (DB SQLite) ← persistence                     │

│     ↓                                                        │

│  6. PointageLogManager ← logs structurés                   │

│                                                              │

└──────────────────────────────────────────────────────────────┘

↓                                    ↓

[Fichier log]                    [Console terminal]

↓

(logs/pointage.log)
┌──────────────────────────────────────────────────────────────┐

│              API REST (Port 8000) - FastAPI                 │

│                                                              │

│  GET /              → Dashboard HTML                         │

│  GET /config        → Config actuelle                        │

│  GET /suivi/jour    → Présence du jour                      │

│  GET /suivi/employe/{id}/semaine  → Semaine                │

│  GET /suivi/employe/{id}/mois     → Mois complet           │

│  WS /ws/pointages   → Stream temps réel                     │

│                                                              │

└──────────────────────────────────────────────────────────────┘

↓

[Navigateur]

Dashboard + WebSocket

---

## Guide de démarrage

### 1. Créer un employé de test

```bash
# Depuis Python
python3 << 'EOF'
import asyncio
from pointage.models import init_db, Employe, get_task_session
from sqlmodel import Session, select, create_engine

# Créer tables
asyncio.run(init_db())

# Insérer employé
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy import create_engine as sync_engine

# Utiliser SQLite sync pour simplifier
engine = sync_engine("sqlite:///~/.local/share/tes_pointeuse/test_pointeuse.db")
emp = Employe(
    id="emp123",
    id_pointeuse="12345",
    prenom="dev",
    nom="Banta",
    heure_arrivee_prevue="08:00",
    heure_depart_prevue="17:00",
    duree_pause_min=60,
)
with SyncSession(engine) as session:
    session.add(emp)
    session.commit()
    print("Employé créé: emp123 (id_pointeuse: 12345)")
EOF
```

### 2. Envoyer des données de test

```bash
# Terminal 3: Envoyer une arrivée
echo "12345,2026-06-18 08:30:15,0,1,0,0" | nc localhost 9999

# Envoyer un départ
echo "12345,2026-06-18 17:30:45,3,1,0,0" | nc localhost 9999
```

### 3. Consulter le résultat

- **Dashboard:** http://localhost:8000
- **API:** http://localhost:8000/suivi/jour
- **Logs:** `tail -f logs/pointage.log`

---

## Format des données

### CSV (défaut)

```csv
id_pointeuse,timestamp,action,statut_badge,extra_1,extra_2
12345,2026-06-18 08:30:15,0,1,0,0
```

**Colonnes:**
- `id_pointeuse` (0): Identifiant du terminal/employé
- `timestamp` (1): Date/heure du badgeage
- `action` (2): 0=arrivée, 1=pause, 2=fin_pause, 3=départ
- `statut_badge` (3): 0=ok, 1=erreur, etc
- `extra_1` (4): Données additionnelles
- `extra_2` (5): Données additionnelles

### JSON

```json
{
  "id_pointeuse": "12345",
  "timestamp": "2026-06-18T08:30:15",
  "action": 0,
  "statut_badge": 1
}
```

---

## Configuration par scénario

### Scénario 1: Test simple
```env
TERMINAL_FORMAT=csv
PAUSE_MODE=system
LOG_LEVEL=DEBUG
POINTAGE_ARRIVEE_MODE=first_only
```

### Scénario 2: Production
```env
TERMINAL_FORMAT=json
PAUSE_MODE=terminal
LOG_LEVEL=WARNING
LOG_OUTPUT=file
CLIENT_TIMEOUT_SEC=600
```

### Scénario 3: Multi-pointeuses
```env
TERMINAL_FORMAT=csv
TERMINAL_DELIMITER=;
TERMINAL_FIELD_MAPPING={"timestamp": 0, "id_pointeuse": 1, "action": 2}
PAUSE_MODE=hybrid
```

---

## API Endpoints

### GET /
Dashboard HTML interactif

### GET /config
Retourne la configuration actuelle

```bash
curl http://localhost:8000/config
```

### WS /ws/pointages
WebSocket pour suivi temps réel

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/pointages');
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data.events); // 50 derniers pointages
};
```

### GET /suivi/jour?date_str=2026-06-18
Présence du jour (tous les employés)

```bash
curl http://localhost:8000/suivi/jour
```

Résultat:
```json
{
  "date": "2026-06-18",
  "jour": "mercredi",
  "total": 25,
  "presents": 20,
  "absents": 3,
  "off_planning": 2,
  "employes": [...]
}
```

### GET /suivi/employe/{id}/semaine?date_ref=2026-06-18
Suivi hebdomadaire d'un employé

### GET /suivi/employe/{id}/mois?annee=2026&mois=6
Suivi mensuel complet d'un employé

---

## Résultats attendus

### Pointage simple (arrivée à 08:30, départ à 17:30)

**Données:**
12345,2026-06-18 08:30:15,0,1,0,0

12345,2026-06-18 17:30:45,3,1,0,0

**Résultat en base:**
```json
{
  "employe_id": "emp123",
  "date_jour": "2026-06-18",
  "heure_arrivee": "08:30",
  "heure_depart": "17:30",
  "statut": "off",
  "retard_arrivee_min": 30,
  "retard_depart_min": 30
}
```

**Dashboard:**
[08:30:15] Arrivée → 08:30 | Retard de 30 min

[17:30:45] Départ → 17:30 | Retard de 30 min

### Avec pauses (mode terminal)

**Données:**
12345,2026-06-18 08:30:15,0,1,0,0  ← arrivée

12345,2026-06-18 13:00:30,1,1,0,0  ← pause

12345,2026-06-18 14:15:45,2,1,0,0  ← fin_pause (+15 min)

12345,2026-06-18 17:30:45,3,1,0,0  ← départ

**Résultat:**
```json
{
  "heure_arrivee": "08:30",
  "heure_pause": "13:00",
  "heure_fin_pause": "14:15",
  "heure_depart": "17:30",
  "heures_travaillees": 8.75
}
```

**Dashboard:**
[08:30] Arrivée → Retard de 30 min

[13:00] Pause → Pause à 13:00

[14:15] Fin pause → AVERTISSEMENT: Pause déviée de +15 min

[17:30] Départ → Retard de 30 min

### Re-badgeage ignoré

**Configuration:**
```env
POINTAGE_ARRIVEE_MODE=first_only
REBADGE_IGNORE_MIN=5
```

**Données:**
08:30:15 ← accepté

08:31:00 ← ignoré (<5 min)

08:35:00 ← accepté (>5 min mais mode=first_only, ignoré quand même)

**Dashboard:**
✓ Arrivée à 08:30

** Re-badage ignoré (même jour)

** Re-badage ignoré (même jour)

---

## Logs

### Format structuré (JSON)

```json
{
  "timestamp": "2026-06-18T08:30:15.123456",
  "level": "INFO",
  "logger": "pointage",
  "message": "[Banta dev] Arrivée → 08:30 | Retard de 30 min"
}
```

### Consulter
```bash
tail -f logs/pointage.log
tail -f logs/pointage.log | jq .
grep "Banta dev" logs/pointage.log
```

---

## Troubleshooting

| Problème | Cause | Solution |
|----------|-------|----------|
| Port 9999 déjà utilisé | Autre processus | `lsof -i :9999 && kill -9 <PID>` |
| "Employe non trouvé" | id_pointeuse introuvable | Créer l'employé en base |
| Logs vides | Données n'arrivent pas | `echo "..." \| nc localhost 9999` |
| Config ne se met à jour pas | Serveur pas redémarré | `Ctrl+C` puis relancer |
| Permission denied sur logs | Droits fichiers | `chmod 755 logs` |
| JSON ne parse pas | Format invalide | Vérifier `TERMINAL_TIMESTAMP_FORMAT` |

---

## Développement

### Structure
pointage/

├── main.py              # Serveur socket principal

├── api.py               # API FastAPI

├── models.py            # SQLModel + init BD

├── config_pointage.py   # Configuration

├── terminal_listener.py # Parser + serveur socket

├── pointage.py          # Dispatcher (logique)

├── logger_pointage.py   # Logs structurés

├── utils.py             # Helpers (retard, pause, persist)

├── utils_planning.py    # Suivi (mois, semaine, jour)

├── env.example          # Exemple config

└── logs/                # Fichiers log

|__terminal_simulator    # Fichier de simumation à demarer


### Ajouter une colonne au CSV

1. Modifier `TERMINAL_FIELD_MAPPING` dans .env
2. Relancer le serveur
3. Exemple: ajouter colonnes "température" et "localisation"
```env
TERMINAL_FIELD_MAPPING={"id_pointeuse": 0, "timestamp": 1, "action": 2, "statut_badge": 3, "temperature": 4, "location": 5}
```

### Ajouter une métrique

1. Modifier `_process_pointage()` dans `pointage.py`
2. Ajouter le calcul
3. Ajouter à `result["your_metric"]`
4. Sauvegarder en base via `db_upsert_pointage()`

---

## Performances

- **Débit:** ~1000 pointages/seconde
- **Mémoire:** ~50MB (logs en mémoire pour WebSocket)
- **Latence:** <10ms parse + dispatch
- **Storage:** ~500KB par jour (500 employés)

---

## Sécurité

- Pas d'authentification (utiliser derrière reverse proxy en production)
- Pas de chiffrement (réseau local recommandé)
- Logs en clair (sensibles à la confidentialité)
{ NB ///reseau local ferme uniquement}

**Pour production:**
1. Ajouter API key
2. HTTPS/TLS
3. Firewall IP
4. Rotation des logs

---

## FAQ

**Q: Comment supprimer un pointage?**
A: Supprimer directement de la base (pas d'API).

**Q: Comment modifier les horaires prévus?**
A: Modifier la table `Employe` (heure_arrivee_prevue, etc) ou créer un `PlanningMensuel`.

**Q: Support du multi-tenant?**
A: Pas pour l'instant. Une instance par entreprise.

**Q: Export des données?**
A: Via API REST en JSON ou direct depuis SQLite.

**Q: Alertes (retards, absences)?**
A: Pas intégré. Implémenter via les logs ou l'API.

---

## Support

- Logs détaillés: `LOG_LEVEL=DEBUG`
- Configuration complète: Voir `env.example`
- Documentation API: http://localhost:8000/docs
- Exemple curl: Voir section API

---