from pointage_prodac.utils import (
    _parse_pause_duration,_mh,calculate_pause_deviation,_retard,
    db_upsert_pointage
)
from pointage_prodac.utils_planning import (
    get_planning_actif,db_update_emp_field,db_get_employe,
)
from typing import Optional,Dict,List,Tuple,Any
from sqlmodel import select
from datetime import date
from pointage_prodac.models import get_task_session, Pointage, Employe
# ═══════════════════════════════════════════════
#  POINTAGE (back-end pur, Les helperspour un test)
# ═══════════════════════════════════════════════
def _row_to_ptg(obj) -> dict:
    """Convertit un objet Pointage SQLModel en dict."""
    if obj is None:
        return {}
    cols = [
        "id", "employe_id","id_pointeuse", "date_jour",
        "heure_arrivee", "heure_pause", "heure_fin_pause", "heure_depart",
        "heure_arrivee_prevue", "heure_pause_prevue", "heure_fin_pause_prevue", "heure_depart_prevue",
        "retard_arrivee_min", "retard_pause_min", "retard_fin_pause_min", "retard_depart_min",
        "absent", "presence_inattendue", "statut", "note",
        "heures_sup_jour", "heures_travaillees_jour", "created_at",
    ]
    return {c: getattr(obj, c, None) for c in cols}



def _row_to_emp(obj) -> dict:
    if obj is None:
        return {}
    cols = [
        "id", "prenom", "nom", "id_pointeuse","photo_b64", "poste", "departement", "date_embauche",
        "type_contrat", "duree_contrat", "salaire", "horaire", "jours_off", "droit_conge",
        "heure_arrivee_prevue", "heure_pause_prevue", "duree_pause_min", "heure_depart_prevue",
        "telephone", "email", "adresse", "date_naissance", "lieu_naissance", "nationalite",
        "type_piece", "num_piece", "date_expiration_piece", "photo_cni_b64", "signature_b64",
        "contrat_pdf_b64", "contrat_signe", "contact_urgence_nom", "contact_urgence_tel",
        "contact_urgence_lien", "statut_jour", "heure_arrivee", "heure_depart", "actif",
        "created_at", "email_interne", "password_hash",
        # ← nouveaux
        "mode_salaire", "taux_horaire", "date_fin_periode_essai",
        "mode_travail", "score_evaluation", "kpi_atteint",
    ]
    emp = {c: getattr(obj, c, None) for c in cols}
    emp["matricule"] = (emp.get("id") or "")[:8].upper()
    # Calculer en_periode_essai depuis la date
    dfe = emp.get("date_fin_periode_essai")
    if dfe:
        from datetime import date
        try:
            emp["en_periode_essai"] = date.fromisoformat(dfe) >= date.today()
        except Exception:
            emp["en_periode_essai"] = False
    else:
        emp["en_periode_essai"] = False
    return emp



async def db_get_pointage_today(emp_id: str, cible_date: str = None, session=None) -> Optional[dict]:
    d = cible_date if cible_date else date.today().isoformat()
    async with get_task_session() as new_session:
        stmt = select(Pointage).where(
            Pointage.employe_id == emp_id,
            Pointage.date_jour == d
        )
        result = await new_session.execute(stmt)
        pointage_obj = result.scalar_one_or_none()

    data = _row_to_ptg(pointage_obj) if pointage_obj else None
    return data



async def get_schedule_for_employee_db(
    employe_id: str,
    jour: str,
    pour_date: date = None,
) -> dict:
    """
    Résout le planning d'un employé pour un jour donné.
    Priorité : planning mensuel > hebdomadaire > horaires par défaut de l'employé.
    """
    if pour_date is None:
        pour_date = date.today()

    annee = pour_date.year
    mois = pour_date.month
    jour = jour.lower().strip()

    async with get_task_session() as session:
        # Appel à la source de vérité unique
        planning_obj, source = await get_planning_actif(
            session,employe_id, annee, mois
        )

        if planning_obj is not None:
            return {
                "debut":  getattr(planning_obj, f"{jour}_debut", "OFF"),
                "fin":    getattr(planning_obj, f"{jour}_fin",   "OFF"),
                "pause":  getattr(planning_obj, f"{jour}_pause", "OFF"),
                "source": source,
            }

    # Aucun planning du tout (même pas d'employé) → OFF
    return {"debut": "OFF", "fin": "OFF", "pause": "OFF", "source": "defaut"}


async def faire_pointage(emp: dict, action: str, heure: str, session=None) -> dict:

    emp_id        = emp.get("id", "")
    today         = date.today()
    jours = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    jour_semaine  = jours[today.weekday()]

    # ← REMPLACE get_employee_schedule_by_id — requête DB directe
    schedule = await get_schedule_for_employee_db(
        employe_id=emp_id,
        jour=jour_semaine,
        pour_date=today,
    )

    if schedule and schedule.get("debut") != "OFF":
        sched_debut    = schedule["debut"]
        sched_fin      = schedule["fin"]
        sched_pause    = schedule["pause"]
        sched_pause_min = _parse_pause_duration(sched_pause)
    else:
        sched_debut    = emp.get("heure_arrivee_prevue", "08:00")
        sched_fin      = emp.get("heure_depart_prevue",  "17:00")
        raw_dur        = emp.get("duree_pause_min")
        sched_pause_min = int(raw_dur) if raw_dur not in (None, "", 0) else 30
        sched_pause    = f"{sched_pause_min}min"

    pause_start_scheduled = emp.get("heure_pause_prevue", "13:00")
    fp_prev = _mh(_hm(pause_start_scheduled) + sched_pause_min)

    # ── Charger le pointage existant 
    ptg = await db_get_pointage_today(emp_id, session=session) or {
        "employe_id": emp_id,
        "date_jour": today.isoformat(),
        "heure_arrivee_prevue": sched_debut,
        "heure_pause_prevue": pause_start_scheduled,
        "heure_fin_pause_prevue": fp_prev,
        "heure_depart_prevue": sched_fin,
    }

    retard = 0
    pause_deviation = 0
    pause_message = ""
    nouveau_statut = emp.get("statut_jour", "off")
    action_ignoree = False   # ← flag silencieux

    if action == "arrivee":
        if not ptg.get("heure_arrivee"):           # ← guard : 1ère fois seulement
            ptg["heure_arrivee"] = heure
            retard = _retard(heure, ptg.get("heure_arrivee_prevue", sched_debut))
            ptg["retard_arrivee_min"] = retard
            nouveau_statut = "travail"
            ptg["absent"] = 0
        else:
            # Déjà pointé → on retourne le statut actuel sans rien modifier
            action_ignoree = True
            nouveau_statut = ptg.get("statut", emp.get("statut_jour", "travail"))
            retard = ptg.get("retard_arrivee_min", 0)

    elif action == "pause":
        if not ptg.get("heure_pause"):             # ← guard
            ptg["heure_pause"] = heure
            ptg["retard_pause_min"] = 0
            nouveau_statut = "pause"
        else:
            action_ignoree = True
            nouveau_statut = ptg.get("statut", "pause")

    elif action == "fin_pause":
        if not ptg.get("heure_fin_pause"):          # ← guard
            ptg["heure_fin_pause"] = heure
            pause_start = ptg.get("heure_pause", "")
            if pause_start and sched_pause_min > 0:
                pause_dev_result = calculate_pause_deviation(pause_start, heure, sched_pause)
                pause_deviation = pause_dev_result.get("deviation", 0)
                pause_message = pause_dev_result.get("message", "")
            retard = _retard(heure, ptg.get("heure_fin_pause_prevue", fp_prev))
            ptg["retard_fin_pause_min"] = retard
            nouveau_statut = "travail"
        else:
            action_ignoree = True
            nouveau_statut = ptg.get("statut", "travail")
            retard = ptg.get("retard_fin_pause_min", 0)

    elif action == "depart":
        if not ptg.get("heure_depart"):             # ← guard
            ptg["heure_depart"] = heure
            retard = _retard(heure, ptg.get("heure_depart_prevue", sched_fin))
            ptg["retard_depart_min"] = retard
            nouveau_statut = "off"
        else:
            action_ignoree = True
            nouveau_statut = ptg.get("statut", "off")
            retard = ptg.get("retard_depart_min", 0)

    # ── Sauvegarder seulement si quelque chose a change// ici cela eviter de rebadger arrive si la personne deja badge arrive 
    if not action_ignoree:
        ptg["statut"] = nouveau_statut
        await db_upsert_pointage(ptg, session=session)
        await db_update_emp_field(
            emp_id,
            session=session,
            statut_jour=nouveau_statut,
            heure_arrivee=ptg.get("heure_arrivee", ""),
            heure_depart=ptg.get("heure_depart", ""),
        )

    # ── Construction du message retour 
    labels = {
        "arrivee":   "Arrivée",
        "pause":     "Début pause",
        "fin_pause": "Fin pause",
        "depart":    "Départ fin de journée",
    }
    abs_r = abs(retard)

    if action_ignoree:
        msg = "ℹ Déjà enregistré pour aujourd'hui"
    elif action == "fin_pause" and pause_message:
        if pause_deviation > 0:
            msg = f"⚠ {pause_message}"
        elif pause_deviation < 0:
            msg = f"✓ Pause raccourcie de {abs(pause_deviation)} min"
        else:
            msg = "✓ Pause normale"
    elif retard > 1:
        msg = f"⚠ Retard de {abs_r} min"
    elif retard < -1:
        msg = f"✓ En avance de {abs_r} min"
    else:
        msg = "✓ À l'heure"

    return {
        "ok": True,                               # toujours True — jamais d'erreur
        "heure": heure,
        "action": labels.get(action, action),
        "action_ignoree": action_ignoree,         # le front peut afficher un toast discret
        "retard_min": retard,
        "pause_deviation": pause_deviation,
        "pause_message": pause_message,
        "message": msg,
        "statut": nouveau_statut,
        "scheduled_debut": sched_debut,
        "scheduled_fin": sched_fin,
        "scheduled_pause": sched_pause_min,
    }
