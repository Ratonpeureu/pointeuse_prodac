from typing import Dict
from pointage_prodac.models import Pointage
from datetime import date
from pointage_prodac.utils_planning import db_upsert_pointage
from pointage_prodac.models import get_task_session
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import select

_schedule_file_path: str = ""
_schedule_data: Dict[str, Dict[str, str]] = {}

DAY_COLUMNS = {
    "lundi": {"debut": 1, "fin": 2, "pause": 3},
    "mardi": {"debut": 4, "fin": 5, "pause": 6},
    "mercredi": {"debut": 7, "fin": 8, "pause": 9},
    "jeudi": {"debut": 10, "fin": 11, "pause": 12},
    "vendredi": {"debut": 13, "fin": 14, "pause": 15},
    "samedi": {"debut": 16, "fin": 17, "pause": 18},
    "dimanche": {"debut": 19, "fin": 20, "pause": 21},
}


async def _persist_pointage(employe: dict, result: dict):
    """Sauvegarde le pointage en base"""
    
    today = date.today().isoformat()
    ptg_data = result["ptg_updated"]
    
    ptg_record = {
        "employe_id": employe["id"],
        "date_jour": today,
        "heure_arrivee": ptg_data.get("heure_arrivee", ""),
        "heure_pause": ptg_data.get("heure_pause", ""),
        "heure_fin_pause": ptg_data.get("heure_fin_pause", ""),
        "heure_depart": ptg_data.get("heure_depart", ""),
        "statut": ptg_data.get("statut", "off"),
    }
    
    async with get_task_session() as session:
        stmt = insert(Pointage).values(**ptg_record)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in Pointage.__table__.columns
            if c.name not in ["id", "created_at"] and c.name in ptg_record
        }
        upsert_stmt = stmt.on_conflict_do_update(index_elements=['id'], set_=update_cols)
        await session.execute(upsert_stmt)
        await session.commit()


def _parse_pause_duration(pause_str: str) -> int:
    if not pause_str or pause_str.upper() == "OFF":
        return 0
    pause_str = pause_str.strip().lower()
    if "h" in pause_str:
        parts = pause_str.replace("h", ":").split(":")
        hours = int(parts[0]) if parts[0] else 0
        minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        return hours * 60 + minutes
    else:
        try:
            return int(pause_str.replace("min", "").strip())
        except:
            return 0

def _parse_time(time_str: str) -> str:
    if not time_str or time_str.upper() == "OFF":
        return "OFF"
    time_str = time_str.strip().lower().replace("h", ":")
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            return f"{h:02d}:{m:02d}"
        else:
            h = int(time_str)
            return f"{h:02d}:00"
    except:
        return "OFF"


def _hm(s: str) -> int:
    try:
        h, m = s.strip().split(":")
        return int(h) * 60 + int(m)
    except:
        return 0

def _mh(m: int) -> str:
    return f"{m//60:02d}:{m%60:02d}"

def _retard(reel: str, prevu: str) -> int:
    if not reel or not prevu:
        return 0
    return _hm(reel) - _hm(prevu)

def calculate_pause_deviation(pause_start: str, pause_end: str, scheduled_pause: str) -> dict:
    if not pause_start or not pause_end or pause_start == "OFF" or pause_end == "OFF":
        return {"deviation": 0, "message": "", "is_warning": False}
    start_min = _hm(pause_start)
    end_min = _hm(pause_end)
    actual_duration = end_min - start_min
    if actual_duration < 0:
        actual_duration += 24 * 60
    scheduled_minutes = _parse_pause_duration(scheduled_pause)
    if scheduled_minutes == 0:
        return {"deviation": 0, "message": "", "is_warning": False}
    deviation = actual_duration - scheduled_minutes
    if deviation > 0:
        return {"deviation": deviation, "message": f"+{deviation}min pause", "is_warning": True, "exceeded": True}
    elif deviation < 0:
        return {"deviation": deviation, "message": f"{deviation}min pause (réduite)", "is_warning": True, "exceeded": False}
    else:
        return {"deviation": 0, "message": "PauseOK", "is_warning": False}
