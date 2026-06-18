from datetime import date, timedelta
from typing import Optional
import calendar
from sqlmodel import select
from pointage_prodac.models import (
    Pointage, Employe, PlanningHebdomadaire, PlanningMensuel,
    get_task_session
)
from sqlalchemy.dialects.postgresql import insert
from pointage_prodac.models import gen_id
from sqlalchemy import update
from datetime import datetime
from pointage_prodac.models import get_task_session, Pointage, Employe, gen_id
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert


JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]


def _jour_semaine(d: date) -> str:
    return JOURS[d.weekday()]


def _planning_jour(planning, jour: str) -> dict:
    """Extrait debut/fin/pause pour un jour depuis un objet planning DB."""
    if not planning:
        return {"debut": "OFF", "fin": "OFF", "pause": "OFF"}
    return {
        "debut": getattr(planning, f"{jour}_debut", "OFF"),
        "fin":   getattr(planning, f"{jour}_fin",   "OFF"),
        "pause": getattr(planning, f"{jour}_pause",  "OFF"),
    }

async def get_planning_actif(
    session, employe_id: str, annee: int, mois: int
):
    """Retourne le planning actif (mensuel > hebdo > synthétique depuis l'employé)."""
    mensuel_query = select(PlanningMensuel).where(
        PlanningMensuel.employe_id    == employe_id,
        PlanningMensuel.annee         == annee,
        PlanningMensuel.mois          == mois,
    ).order_by(PlanningMensuel.updated_at.desc())  # on garde le plus récent

    mensuel = (await session.execute(mensuel_query)).scalars().first()
    if mensuel:
        return mensuel, "mensuel"

    # 2. Planning hebdomadaire (protection anti‑doublon)
    hebdo_query = select(PlanningHebdomadaire).where(
        PlanningHebdomadaire.employe_id    == employe_id,
    ).order_by(PlanningHebdomadaire.updated_at.desc())

    hebdo = (await session.execute(hebdo_query)).scalars().first()
    if hebdo:
        return hebdo, "hebdomadaire"

    # 3. Synthétique depuis l'employé (inchangé)
    emp = (await session.execute(
        select(Employe).where(
            Employe.id == employe_id,
        )
    )).scalar_one_or_none() 

    if not emp:
        return None, "aucun"

    # Déterminer les jours off de l'employé
    jours_off = set()
    off_str = (emp.jours_off or "Sam, Dim").lower().replace(",", " ").split()
    mapping = {"lun":0,"mar":1,"mer":2,"jeu":3,"ven":4,"sam":5,"dim":6}
    for part in off_str:
        for key, val in mapping.items():
            if part.startswith(key):
                jours_off.add(val)

    # Heures par défaut
    debut = emp.heure_arrivee_prevue or "08:00"
    fin   = emp.heure_depart_prevue  or "17:00"
    pause = f"{emp.duree_pause_min or 60}min"

    # Construire un objet "faux planning" avec les attributs nécessaires
    class PlanningSynthetique:
        pass

    planning = PlanningSynthetique()
    for i, jour in enumerate(JOURS):
        if i in jours_off:
            setattr(planning, f"{jour}_debut", "OFF")
            setattr(planning, f"{jour}_fin",   "OFF")
            setattr(planning, f"{jour}_pause", "OFF")
        else:
            setattr(planning, f"{jour}_debut", debut)
            setattr(planning, f"{jour}_fin",   fin)
            setattr(planning, f"{jour}_pause", pause)

    return planning, "employe"

async def suivi_mensuel_employe(
    employe_id: str,
    annee: int,
    mois: int,
) -> dict:
    """
    Suivi complet d'un employé pour un mois :
    - Jours prévus selon planning (excluant jours OFF)
    - Jours pointés (présence réelle)
    - Absences (prévu mais pas pointé)
    - Retards
    - Détail jour par jour
    """
    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])
    aujourd_hui  = date.today()

    async with get_task_session() as session:
        # Planning actif
        planning, source_planning = await get_planning_actif(
            session, employe_id, annee, mois
        )

        # Tous les pointages du mois
        pointages_db = (await session.execute(
            select(Pointage).where(
                Pointage.employe_id    == employe_id,
                Pointage.date_jour     >= premier_jour.isoformat(),
                Pointage.date_jour     <= dernier_jour.isoformat(),
            )
        )).scalars().all()

        # Infos employé
        emp = (await session.execute(
            select(Employe).where(
                Employe.id == employe_id,
            )
        )).scalar_one_or_none()

    # Index pointages par date
    ptg_idx = {p.date_jour: p for p in pointages_db}

    jours_prevus   = 0
    jours_presents = 0
    jours_absents  = 0
    jours_off_planning = 0
    total_retard_min   = 0
    details = []

    # Parcourir tous les jours du mois jusqu'à aujourd'hui
    d = premier_jour
    while d <= min(dernier_jour, aujourd_hui):
        jour_semaine = _jour_semaine(d)
        sched = _planning_jour(planning, jour_semaine)
        d_str = d.isoformat()

        # Jour OFF selon planning
        if sched["debut"] == "OFF":
            jours_off_planning += 1
            details.append({
                "date":          d_str,
                "jour":          jour_semaine,
                "prevu":         False,
                "statut":        "off_planning",
                "heure_arrivee": None,
                "heure_depart":  None,
                "retard_min":    0,
                "note":          "Jour non travaillé selon planning",
            })
            d += timedelta(days=1)
            continue

        jours_prevus += 1
        ptg = ptg_idx.get(d_str)

        if ptg and ptg.heure_arrivee:
            jours_presents += 1
            retard = ptg.retard_arrivee_min or 0
            total_retard_min += max(0, retard)
            statut = ptg.statut or "travail"
            details.append({
                "date":          d_str,
                "jour":          jour_semaine,
                "prevu":         True,
                "statut":        statut,
                "prevu_debut":   sched["debut"],
                "prevu_fin":     sched["fin"],
                "heure_arrivee": ptg.heure_arrivee,
                "heure_depart":  ptg.heure_depart,
                "retard_min":    retard,
                "heures_travaillees": ptg.heures_travaillees_jour or 0,
                "heures_sup":    ptg.heures_sup_jour or 0,
                "note":          ptg.note or "",
            })
        else:
            jours_absents += 1
            details.append({
                "date":          d_str,
                "jour":          jour_semaine,
                "prevu":         True,
                "statut":        "absent",
                "prevu_debut":   sched["debut"],
                "prevu_fin":     sched["fin"],
                "heure_arrivee": None,
                "heure_depart":  None,
                "retard_min":    0,
                "note":          "Absence non justifiée",
            })

        d += timedelta(days=1)

    taux_presence = round(
        (jours_presents / jours_prevus * 100) if jours_prevus > 0 else 0, 1
    )

    return {
        "employe_id":       employe_id,
        "nom":              f"{emp.prenom} {emp.nom}" if emp else "",
        "poste":            emp.poste if emp else "",
        "annee":            annee,
        "mois":             mois,
        "source_planning":  source_planning,
        "jours_prevus":     jours_prevus,
        "jours_presents":   jours_presents,
        "jours_absents":    jours_absents,
        "jours_off_planning": jours_off_planning,
        "taux_presence_pct": taux_presence,
        "total_retard_min": total_retard_min,
        "details":          details,
    }


async def suivi_semaine_employe(
    employe_id: str,
    date_ref: Optional[str] = None,
) -> dict:
    """
    Suivi de la semaine contenant date_ref (ou semaine courante).
    """
    ref = date.fromisoformat(date_ref) if date_ref else date.today()
    # Lundi de la semaine
    lundi = ref - timedelta(days=ref.weekday())
    dimanche = lundi + timedelta(days=6)

    async with get_task_session() as session:
        planning, source = await get_planning_actif(
            session, employe_id, lundi.year, lundi.month
        )

        pointages_db = (await session.execute(
            select(Pointage).where(
                Pointage.employe_id    == employe_id,
                Pointage.date_jour     >= lundi.isoformat(),
                Pointage.date_jour     <= dimanche.isoformat(),
            )
        )).scalars().all()

        emp = (await session.execute(
            select(Employe).where(
                Employe.id == employe_id,
            )
        )).scalar_one_or_none()

    ptg_idx   = {p.date_jour: p for p in pointages_db}
    aujourd_hui = date.today()
    details   = []
    presents  = absents = 0

    for i in range(7):
        d = lundi + timedelta(days=i)
        jour = JOURS[d.weekday()]
        sched = _planning_jour(planning, jour)
        d_str = d.isoformat()

        if sched["debut"] == "OFF":
            details.append({
                "date": d_str, "jour": jour,
                "statut": "off_planning",
                "prevu_debut": "OFF", "prevu_fin": "OFF",
                "heure_arrivee": None, "heure_depart": None,
            })
            continue

        if d > aujourd_hui:
            details.append({
                "date": d_str, "jour": jour,
                "statut": "futur",
                "prevu_debut": sched["debut"], "prevu_fin": sched["fin"],
                "heure_arrivee": None, "heure_depart": None,
            })
            continue

        ptg = ptg_idx.get(d_str)
        if ptg and ptg.heure_arrivee:
            presents += 1
            details.append({
                "date": d_str, "jour": jour,
                "statut": ptg.statut or "travail",
                "prevu_debut": sched["debut"], "prevu_fin": sched["fin"],
                "heure_arrivee": ptg.heure_arrivee,
                "heure_depart":  ptg.heure_depart,
                "retard_min":    ptg.retard_arrivee_min or 0,
                "heures_travaillees": ptg.heures_travaillees_jour or 0,
            })
        else:
            absents += 1
            details.append({
                "date": d_str, "jour": jour,
                "statut": "absent",
                "prevu_debut": sched["debut"], "prevu_fin": sched["fin"],
                "heure_arrivee": None, "heure_depart": None,
            })

    return {
        "employe_id":  employe_id,
        "nom":         f"{emp.prenom} {emp.nom}" if emp else "",
        "semaine_du":  lundi.isoformat(),
        "semaine_au":  dimanche.isoformat(),
        "source_planning": source,
        "jours_presents": presents,
        "jours_absents":  absents,
        "details":        details,
    }


async def suivi_jour_tous_employes(
    date_str: Optional[str] = None,
) -> dict:
    """
    Vue journalière RH : tous les employés avec leur statut vs planning.
    """
    d = date.fromisoformat(date_str) if date_str else date.today()
    d_str = d.isoformat()
    jour  = _jour_semaine(d)

    async with get_task_session() as session:
        emps = (await session.execute(
            select(Employe).where(
                Employe.actif == 1
            ).order_by(Employe.nom)
        )).scalars().all()

        ptgs = (await session.execute(
            select(Pointage).where(
                Pointage.date_jour     == d_str,
            )
        )).scalars().all()

        mensuels = (await session.execute(
            select(PlanningMensuel).where(
                PlanningMensuel.annee == d.year,
                PlanningMensuel.mois  == d.month,
            )
        )).scalars().all()

        hebdos = (await session.execute(
            select(PlanningHebdomadaire).where(
            )
        )).scalars().all()

    ptg_idx     = {p.employe_id: p for p in ptgs}
    mensuel_idx = {p.employe_id: p for p in mensuels}
    hebdo_idx   = {p.employe_id: p for p in hebdos}

    presents = absents = off_planning = 0
    employes = []

    for emp in emps:
        planning, _ = await get_planning_actif(session, emp.id, d.year, d.month)
        sched = _planning_jour(planning, jour)
        ptg      = ptg_idx.get(emp.id)

        if sched["debut"] == "OFF":
            off_planning += 1
            statut = "off_planning"
        elif ptg and ptg.heure_arrivee:
            presents += 1
            statut = ptg.statut or "travail"
        else:
            absents += 1
            statut = "absent"

        employes.append({
            "employe_id":    emp.id,
            "matricule":     emp.id[:8].upper(),
            "nom":           emp.nom,
            "prenom":        emp.prenom,
            "poste":         emp.poste,
            "statut":        statut,
            "prevu_debut":   sched["debut"],
            "prevu_fin":     sched["fin"],
            "heure_arrivee": ptg.heure_arrivee if ptg else None,
            "heure_depart":  ptg.heure_depart  if ptg else None,
            "retard_min":    (ptg.retard_arrivee_min or 0) if ptg else 0,
        })

    return {
        "date":        d_str,
        "jour":        jour,
        "total":       len(emps),
        "presents":    presents,
        "absents":     absents,
        "off_planning": off_planning,
        "employes":    employes,
    }


async def db_upsert_pointage(ptg: dict, session=None) -> dict:
    if not ptg.get("id"):
        ptg["id"] = gen_id()
    if not ptg.get("created_at"):
        ptg["created_at"] = datetime.now().isoformat()

    if session is not None:
        stmt = insert(Pointage).values(**ptg)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in Pointage.__table__.columns
            if c.name not in ["id", "created_at"] and c.name in ptg
        }
        upsert_stmt = stmt.on_conflict_do_update(index_elements=['id'], set_=update_cols)
        await session.execute(upsert_stmt)
        await session.commit()
    else:
        async with get_task_session() as new_session:
            stmt = insert(Pointage).values(**ptg)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in Pointage.__table__.columns
                if c.name not in ["id", "created_at"] and c.name in ptg
            }
            upsert_stmt = stmt.on_conflict_do_update(index_elements=['id'], set_=update_cols)
            await new_session.execute(upsert_stmt)
            await new_session.commit()

    return ptg



# ── Mise à jour champ employe /// aPour le moment fixe
async def db_update_emp_field(emp_id: str, session=None, **fields):
    if not fields:
        return
    if session is not None:
        stmt = (
            update(Employe)
            .where(Employe.id == emp_id)
            .values(**fields)
        )
        await session.execute(stmt)
        await session.commit()
    else:
        async with get_task_session() as new_session:
            stmt = (
                update(Employe)
                .where(Employe.id == emp_id)
                .values(**fields)
            )
            await new_session.execute(stmt)
            await new_session.commit()


async def db_get_employe(emp_id: str, session=None) -> Optional[dict]:
    if session is not None:
        stmt = select(Employe).where(Employe.id == emp_id)
        result = await session.execute(stmt)
        employe = result.scalar_one_or_none()
    else:
        async with get_task_session() as new_session:
            stmt = select(Employe).where(Employe.id == emp_id)
            result = await new_session.execute(stmt)
            employe = result.scalar_one_or_none()
    result = _row_to_emp(employe) if employe else None
    return result




    