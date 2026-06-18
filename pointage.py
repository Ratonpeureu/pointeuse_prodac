from __future__ import annotations
import asyncio
import calendar as _cal
from typing import Dict, List, Optional, Tuple

from sqlmodel import select
from pointage_prodac.models import get_task_session,Employe
from pointage_prodac.config import faire_pointage, _row_to_emp
import logging
from datetime import datetime, date, timedelta
from pointage_prodac.config_pointage import config
from pointage_prodac.utils import _persist_pointage
from pointage_prodac.logger_pointage import log_manager
from pointage_prodac.utils_planning import get_planning_actif

logger = logging.getLogger(__name__)

# ── Statut labels / colors (for frontend) ────────────────────────────────────
_STATUT_LABEL = {"travail": "EN SERVICE", "pause": "EN PAUSE", "off": "ABSENT"}
_STATUT_COLOR = {"travail": "success", "pause": "warn", "off": "muted"}

# ── Helpers ──────────────────────────────────────────────────────────────────
def _get_emp_key(emp: dict) -> str:
    """Return a unique key (id) for an employee dict."""
    return emp.get("id", "")

async def db_get_employes(actif_only=True) -> List[dict]:
    async with  get_task_session() as session:
        stmt_q = select(Employe).order_by(Employe.nom)
        if actif_only:
            stmt_q = stmt_q.where(Employe.actif == 1)
        result = await session.execute(stmt_q)
        employes = result.scalars().all()
    result = [_row_to_emp(e) for e in employes]
    return result





class PointageDispatcher:
    
    def __init__(self, enterprise_id: str = None):
        self.pause_cfg = config.pause
        self.pointage_cfg = config.pointage
        self.action_map = config.enterprise.action_codes
        
        # Cache des pointages du jour (pour re-badge detection)
        self._daily_cache: Dict[str, dict] = {}
    
    async def handle_terminal_event(self, event) -> Dict:
        """
        Traite un événement terminal avec les règles de config.
        """
        try:

            # 1. Trouver l'employé
            employe = await self._find_employe(event.id_pointeuse)
            if not employe:
                logger.warning(f"Employe non trouve: {event.id_pointeuse}")
                return {
                    "ok": False,
                    "error": f"Employe non trouve: {event.id_pointeuse}",
                    "timestamp": event.timestamp.isoformat(),
                }
            
            # 2. Déterminer le statut actuel
            today = date.today()
            cache_key = f"{employe['id']}_{today.isoformat()}"
            current_ptg = self._daily_cache.get(cache_key) or \
                         await self._load_today_pointage(employe["id"])
            
            # 3. Appliquer les règles de re-badge
            if self._should_ignore_rebadge(current_ptg, event):
                logger.info(
                    f" Re-badage ignoré: {employe['nom']} "
                    f"({event.action_name}) - {event.timestamp.strftime('%H:%M')}"
                )
                return {
                    "ok": True,
                    "ignored": True,
                    "message": "Re-badage ignoré (même jour)",
                    "timestamp": event.timestamp.isoformat(),
                }
            

            # 4. Traiter selon le mode (pause terminal vs système)
            result = await self._process_pointage(employe, event, current_ptg)
            
            if result["ok"] and not result.get("ignored"):
                await _persist_pointage(employe, result)
                self._daily_cache[cache_key] = result["ptg_updated"]
                
                log_manager.log_pointage(
                    employe_id=employe["id"],
                    employe_name=f"{employe['prenom']} {employe['nom']}",
                    action=result.get("action", "?"),
                    heure=result.get("heure", "?"),
                    statut=result.get("statut", "?"),
                    message=result.get("message", ""),
                    warning=result.get("warning"),
                )
            
            # 5. Sauvegarder et logger
            if result["ok"] and not result.get("ignored"):
                await _persist_pointage(employe, result)
                self._daily_cache[cache_key] = result["ptg_updated"]
            
            return result
        
        except Exception as e:
            logger.exception(f" Erreur dispatcheuse pointage...: {e}")
            return {"ok": False, "error": str(e)}
    
    def _should_ignore_rebadge(
        self,
        current_ptg: Optional[dict],
        event
    ) -> bool:
        """
        Logique de re-badage selon config
        """
        if not current_ptg or not current_ptg.get("heure_arrivee"):
            return False  # Première entrée du jour
        
        mode_arrivee = self.pointage_cfg.mode_arrivee
        
        if event.action_name == "arrivee":
            # Mode FIRST_ONLY : ignorer si déjà pointé
            if mode_arrivee == "first_only" and current_ptg.get("heure_arrivee"):
                time_since_first = (event.received_at - current_ptg["_received_at"]).total_seconds() / 60
                if time_since_first < self.pointage_cfg.ignore_rebadge_within_min:
                    return True
        
        elif event.action_name == "depart":
            # Mode LAST_ONLY : toujours accepter (updater le dernier)
            if self.pointage_cfg.mode_depart == "last_only":
                return False
        
        return False
    
    async def _process_pointage(
        self, employe: dict, event, current_ptg: Optional[dict]
    ) -> Dict:
        """
        Traite le pointage selon le mode pause (terminal vs système).
        """
        today = date.today()
        heure = event.timestamp.strftime("%H:%M")
        
        # Initialiser si nécessaire
        if not current_ptg:
            current_ptg = {
                "employe_id": employe["id"],
                "date_jour": today.isoformat(),
                "statut": "off",
            }
        
        result = {
            "ok": True,
            "heure": heure,
            "action": event.action_name,
            "timestamp": event.timestamp.isoformat(),
            "statut": current_ptg.get("statut", "off"),
            "_received_at": event.received_at,
        }
        
        # ═ Logique selon le mode pause
        if event.action_name == "arrivee":
            current_ptg["heure_arrivee"] = heure
            current_ptg["statut"] = "travail"
            result["statut"] = "travail"
            result["message"] = f"✓ Arrivée à {heure}"
        
        elif event.action_name == "pause":
            if self.pause_cfg.mode in ["terminal", "hybrid"]:
                current_ptg["heure_pause"] = heure
                current_ptg["statut"] = "pause"
                result["statut"] = "pause"
                result["message"] = f"⏸ Pause à {heure}"
            else:
                result["ignored"] = True
                result["message"] = "Pause gérée par système (ignorée)"
        
        elif event.action_name == "fin_pause":
            if self.pause_cfg.mode in ["terminal", "hybrid"]:
                pause_start = current_ptg.get("heure_pause", "")
                current_ptg["heure_fin_pause"] = heure
                current_ptg["statut"] = "travail"
                result["statut"] = "travail"
                
                # Détecter écart pause
                if pause_start:
                    deviation = self._calculate_pause_deviation(
                        pause_start, heure,
                        self.pause_cfg.default_duration_min
                    )
                    if abs(deviation) > self.pause_cfg.warn_if_over_min:
                        result["warning"] = f"Pause déviée de {deviation:+d} min"
                
                result["message"] = f"⏵ Reprise à {heure}"
            else:
                result["ignored"] = True
                result["message"] = "Pause gérée par système"
        
        elif event.action_name == "depart":
            current_ptg["heure_depart"] = heure
            current_ptg["statut"] = "off"
            result["statut"] = "off"
            result["message"] = f"$$$$***** Départ à {heure}"
        
        result["ptg_updated"] = current_ptg
        return result
    
    def _calculate_pause_deviation(self, start: str, end: str, expected_min: int) -> int:
        """Retourne déviation en minutes"""
        try:
            h_s, m_s = map(int, start.split(":"))
            h_e, m_e = map(int, end.split(":"))
            actual = (h_e * 60 + m_e) - (h_s * 60 + m_s)
            return actual - expected_min
        except:
            return 0
    
    async def _find_employe(self, id_pointeuse: str) -> Optional[dict]:
        """Récupère l'employé par id_pointeuse"""
        async with get_task_session() as session:
            stmt = select(Employe).where(Employe.id_pointeuse == id_pointeuse)
            result = await session.execute(stmt)
            emp = result.scalar_one_or_none()
            
            if emp:
                return {
                    "id": emp.id,
                    "nom": emp.nom,
                    "prenom": emp.prenom,
                    "id_pointeuse": emp.id_pointeuse,
                }
            return None
    
    async def _load_today_pointage(self, emp_id: str) -> Optional[dict]:
        """Charge le pointage du jour s'il existe"""
        from pointage_prodac.models import Pointage
        from datetime import date
        
        today = date.today().isoformat()
        async with get_task_session() as session:
            stmt = select(Pointage).where(
                Pointage.employe_id == emp_id,
                Pointage.date_jour == today
            )
            result = await session.execute(stmt)
            ptg = result.scalar_one_or_none()
            
            if ptg:
                return {
                    "id": ptg.id,
                    "heure_arrivee": ptg.heure_arrivee,
                    "heure_pause": ptg.heure_pause,
                    "heure_fin_pause": ptg.heure_fin_pause,
                    "heure_depart": ptg.heure_depart,
                    "statut": ptg.statut,
                }
            return None
    

class Presence:
    def __init__(self,employe_id,employe_terminal):
        self.employe_id=employe_id
        self.employe_terminal=employe_terminal
        self._emps: List[dict] = []
        self._sel_emp: Optional[dict] = None

        self._cal_month: date = date.today().replace(day=1)
        self._sel_date: date = date.today()

        # Dirty‑flag caches
        self._prev_ns: int = -1
        self._prev_np: int = -1
        self._prev_no: int = -1
        self._prev_day_key: Optional[Tuple[date, tuple]] = None

    def search_employees(self, query: str) -> List[dict]:
        """
        Filter active employees by name, ID prefix, ou phone.
        Case‑insensitive. Returns at most 6 matches.
        """
        q = query.lower().strip()
        if not q:
            return []
        result = []
        for emp in self._emps:
            if (q in emp.get("nom", "").lower()
                or q in emp.get("prenom", "").lower()
                or q in f"{emp.get('prenom', '')} {emp.get('nom', '')}".lower()
                or q in emp.get("id", "")
                or q in emp.get("telephone", "").lower()):
                result.append(emp)
                if len(result) >= 6:
                    break
        return result

    async def select_employee_by_id_pointeur(self, emp_id: str) -> Optional[dict]:
        """
        Select an employee by ID, update internal state.
        Returns the employee dict or None if not found.
        """
        async with get_task_session() as session:
            stmt = session.execute(select(Employe).
                where(Employe.id == emp.id_pointeuse),            
            )
            emp_term = stmt.scalar_one_or_none()
            if not emp_term:
                print("Employe n'a pas encore de profil dans le Terminal de pointage Vous devez d'abord en creer une pour lui")
            for emp in self._emps:
                if emp.get("id") == emp_id:
                    self._sel_emp = emp
                    return emp
            return None

    async def get_selected_employee_status(self) -> dict:
        """Return a simple status dict for the selected employee."""
        await select_employee_by_id_pointeur(self.employe_id)
        emp = self._sel_emp
        st = emp.get("statut_jour", "off")
        return {
            "found": True,
            "prenom": emp.get("prenom", ""),
            "nom": emp.get("nom", ""),
            "id_short": emp.get("id", ""),
            "statut": st,
            "statut_label": _STATUT_LABEL.get(st, st),
            "statut_color": _STATUT_COLOR.get(st, "muted"),
            "heure_arrivee": emp.get("heure_arrivee", ""),
            "heure_depart": emp.get("heure_depart", ""),
        }


    async def _reload(self):
        """Reload employees from DB (filtered by entreprise) and reset caches."""
        self._emps = await db_get_employes(actif_only=True)
        self._prev_ns = self._prev_np = self._prev_no = -1
        self._prev_day_key = None

    def get_stats(self) -> dict:
        """
        Return presence counts for the three statuses.
        Uses a dirty flag to avoid re‑counting on every call.
        """
        ns = sum(1 for e in self._emps if e.get("statut_jour") == "travail")
        np = sum(1 for e in self._emps if e.get("statut_jour") == "pause")
        no = sum(1 for e in self._emps if e.get("statut_jour") == "off")
        self._prev_ns, self._prev_np, self._prev_no = ns, np, no
        return {
            "en_service": ns,
            "en_pause": np,
            "absents": no,
        }

    async def pointage_action(self, action: str) -> dict:
        if not self._sel_emp:
            return {"ok": False, "error": "Aucun employé sélectionné"}


        now = datetime.now().strftime("%H:%M")
        try:
            res = await faire_pointage(emp, action, now)

            # Update local state (optimistic)
            emp["statut_jour"] = res["statut"]
            if action == "arrivee":
                emp["heure_arrivee"] = now
            elif action == "depart":
                emp["heure_depart"] = now

            # Sync with cache
            idx = next((i for i, e in enumerate(self._emps) if _get_emp_key(e) == _get_emp_key(emp)), None)
            if idx is not None:
                self._emps[idx] = emp

            return {"ok": True, "result": res}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}



