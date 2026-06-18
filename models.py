import json
import os
import platform
import uuid
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, List, Optional,Any, Tuple
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import async_sessionmaker
import sqlalchemy as sa
from sqlalchemy import JSON, Column, Date, ForeignKey, LargeBinary, Text, cast
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from sqlmodel import delete as sqldelete
from sqlalchemy import UniqueConstraint
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert

## HELPER #####
def BoolFalse():
    return Field(
        sa_column=Column(sa.Boolean, nullable=False, server_default=sa.false())
    )

def EmptyString():
    return Field(sa_column=Column(sa.String, nullable=False, server_default=""))

def gen_id() -> str:
    return str(uuid.uuid4())

def get_default_expiration():
    return datetime.now() + timedelta(days=7)



class Employe(SQLModel, table=True):
    __tablename__ = "employe"

    id: str = Field("0",primary_key=True)
    id_pointeuse:str =Field("0",index=True,unique=True)
    prenom: str = Field(default="", index=True)
    nom: str = Field(default="", index=True)
    photo_b64: Optional[str] = Field(default=None)
    poste: str = Field(default="")
    departement: str = Field(default="")
    date_embauche: str = Field(default="")
    type_contrat: str = Field(default="CDI")
    duree_contrat: str = Field(default="")
    salaire: str = Field(default="")
    horaire: str = Field(default="")
    jours_off: str = Field(default="Sam, Dim")
    droit_conge: str = Field(default="30 jours/an")

    heure_arrivee_prevue: str = Field(default="08:00")
    heure_pause_prevue: str = Field(default="13:00")
    duree_pause_min: int = Field(default=60)
    heure_depart_prevue: str = Field(default="17:00")

    telephone: str = Field(default="")
    email: str = Field(default="")
    adresse: str = Field(default="")
    date_naissance: str = Field(default="")
    lieu_naissance: str = Field(default="")
    nationalite: str = Field(default="")

    type_piece: str = Field(default="")
    num_piece: str = Field(default="")
    date_expiration_piece: str = Field(default="")
    photo_cni_b64: Optional[str] = Field(default=None)
    signature_b64: Optional[str] = Field(default=None)
    contrat_pdf_b64: Optional[str] = Field(default=None)
    contrat_signe: int = Field(default=0)

    contact_urgence_nom: str = Field(default="")
    contact_urgence_tel: str = Field(default="")
    contact_urgence_lien: str = Field(default="")

    statut_jour: str = Field(default="off")
    heure_arrivee: str = Field(default="")
    heure_depart: str = Field(default="")
    actif: int = Field(default=1, index=True)

    password_hash: str = Field(default="", description="Hash bcrypt du mot de passe")
    email_interne: str = Field(
        default="", index=True, description="Adresse email interne unique"
    )
    mode_salaire: str = Field(default="fixe", description="fixe | horaire")
    taux_horaire: Optional[float] = Field(
        default=None, description="FCFA/heure si mode_salaire='horaire'"
    )

    date_fin_periode_essai: Optional[str] = Field(
        default=None,
        sa_column=Column(sa.Date, nullable=True),
        description="Date de fin de période d'essai (YYYY-MM-DD)",
    )
    mode_travail: str = Field(
        default="presentiel", description="presentiel | remote | hybride"
    )
    # Nouveau — données KPI/évaluation (utilisées par les règles de primes)
    score_evaluation: Optional[float] = Field(
        default=None, description="Score d'évaluation (0–5). Mis à jour par le RH."
    )
    kpi_atteint: Optional[bool] = Field(
        default=None, description="KPI du mois atteint ou non. Mis à jour par le RH."
    )
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())




class Pointage(SQLModel, table=True):
    __tablename__ = "pointage"
    id: str = Field(default_factory=gen_id, primary_key=True)
    employe_id: str = Field(default="", index=True) 
    date_jour: str = Field(index=True)

    heure_arrivee: str = Field(default="")
    heure_pause: str = Field(default="")
    heure_fin_pause: str = Field(default="")
    heure_depart: str = Field(default="")

    heure_arrivee_prevue: str = Field(default="")
    heure_pause_prevue: str = Field(default="")
    heure_fin_pause_prevue: str = Field(default="")
    heure_depart_prevue: str = Field(default="")

    retard_arrivee_min: int = Field(default=0)
    retard_pause_min: int = Field(default=0)
    retard_fin_pause_min: int = Field(default=0)
    retard_depart_min: int = Field(default=0)

    absent: int = Field(default=0)
    presence_inattendue: int = Field(default=0)

    statut: str = Field(default="off")
    note: str = Field(default="")
    heures_sup_jour: float = Field(
        default=0.0, description="Heures sup complètes (ex: 1.0, 2.0 — jamais 0.75)"
    )
    heures_travaillees_jour: float = Field(
        default=0.0, description="Heures réelles totales du jour"
    )

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

######## Gestionnaire de planning util pour le test #######

class PlanningEmploye(SQLModel, table=True):
    """Planning hebdomadaire d'un employé — persisté en base."""

    __tablename__ = "planning_employe"

    id: str = Field(default_factory=gen_id, primary_key=True)
    employe_id: str = Field(foreign_key="employe.id", index=True)
    matricule: str = Field(index=True)  # 8 chars, redondant pour les lookups rapides

    # Horaires par jour — "OFF" si pas travaillé
    lundi_debut: str = Field(default="OFF")
    lundi_fin: str = Field(default="OFF")
    lundi_pause: str = Field(default="OFF")

    mardi_debut: str = Field(default="OFF")
    mardi_fin: str = Field(default="OFF")
    mardi_pause: str = Field(default="OFF")

    mercredi_debut: str = Field(default="OFF")
    mercredi_fin: str = Field(default="OFF")
    mercredi_pause: str = Field(default="OFF")

    jeudi_debut: str = Field(default="OFF")
    jeudi_fin: str = Field(default="OFF")
    jeudi_pause: str = Field(default="OFF")

    vendredi_debut: str = Field(default="OFF")
    vendredi_fin: str = Field(default="OFF")
    vendredi_pause: str = Field(default="OFF")

    samedi_debut: str = Field(default="OFF")
    samedi_fin: str = Field(default="OFF")
    samedi_pause: str = Field(default="OFF")

    dimanche_debut: str = Field(default="OFF")
    dimanche_fin: str = Field(default="OFF")
    dimanche_pause: str = Field(default="OFF")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Dans rh_manager_db.py


class PlanningHebdomadaire(SQLModel, table=True):
    """Planning hebdomadaire par défaut — s'applique si pas de planning mensuel."""
    __tablename__ = "planning_hebdomadaire"
    id: str = Field(default_factory=gen_id, primary_key=True)
    employe_id: str = Field(foreign_key="employe.id", index=True)
    matricule: str = Field(index=True)

    lundi_debut: str = Field(default="OFF")
    lundi_fin: str = Field(default="OFF")
    lundi_pause: str = Field(default="OFF")
    mardi_debut: str = Field(default="OFF")
    mardi_fin: str = Field(default="OFF")
    mardi_pause: str = Field(default="OFF")
    mercredi_debut: str = Field(default="OFF")
    mercredi_fin: str = Field(default="OFF")
    mercredi_pause: str = Field(default="OFF")
    jeudi_debut: str = Field(default="OFF")
    jeudi_fin: str = Field(default="OFF")
    jeudi_pause: str = Field(default="OFF")
    vendredi_debut: str = Field(default="OFF")
    vendredi_fin: str = Field(default="OFF")
    vendredi_pause: str = Field(default="OFF")
    samedi_debut: str = Field(default="OFF")
    samedi_fin: str = Field(default="OFF")
    samedi_pause: str = Field(default="OFF")
    dimanche_debut: str = Field(default="OFF")
    dimanche_fin: str = Field(default="OFF")
    dimanche_pause: str = Field(default="OFF")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PlanningMensuel(SQLModel, table=True):
    """
    Planning mensuel — override le planning hebdomadaire pour un mois donné.
    Une ligne = un employé + un mois.
    """
    __tablename__ = "planning_mensuel"
    __table_args__ = (
        UniqueConstraint(
            "employe_id", "annee", "mois",
            name="uq_planning_mensuel_ent_emp_mois"
        ),
    )

    id: str = Field(default_factory=gen_id, primary_key=True)
    employe_id: str = Field(foreign_key="employe.id", index=True)
    matricule: str = Field(index=True)
    annee: int = Field(index=True)
    mois: int = Field(index=True)  # 1–12

    lundi_debut: str = Field(default="OFF")
    lundi_fin: str = Field(default="OFF")
    lundi_pause: str = Field(default="OFF")
    mardi_debut: str = Field(default="OFF")
    mardi_fin: str = Field(default="OFF")
    mardi_pause: str = Field(default="OFF")
    mercredi_debut: str = Field(default="OFF")
    mercredi_fin: str = Field(default="OFF")
    mercredi_pause: str = Field(default="OFF")
    jeudi_debut: str = Field(default="OFF")
    jeudi_fin: str = Field(default="OFF")
    jeudi_pause: str = Field(default="OFF")
    vendredi_debut: str = Field(default="OFF")
    vendredi_fin: str = Field(default="OFF")
    vendredi_pause: str = Field(default="OFF")
    samedi_debut: str = Field(default="OFF")
    samedi_fin: str = Field(default="OFF")
    samedi_pause: str = Field(default="OFF")
    dimanche_debut: str = Field(default="OFF")
    dimanche_fin: str = Field(default="OFF")
    dimanche_pause: str = Field(default="OFF")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)




def get_db_path():
    app_name = "tes_pointeuse"
    if platform.system() == "Windows":
        base_path = os.path.join(os.environ.get("APPDATA"), app_name)
    else:
        base_path = os.path.expanduser(f"~/.local/share/{app_name}")
    if not os.path.exists(base_path):
        os.makedirs(base_path)
    return os.path.join(base_path, "test_pointeuse.db")


# Moteur asynchrone UNIQUE
DB_URL = f"sqlite+aiosqlite:///{get_db_path()}"
async_engine = create_async_engine(DB_URL, echo=False, pool_size=30, max_overflow=40)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

def init_task_status():
    SQLModel.metadata.create_all(sync_engine, tables=[TaskStatus.__table__])

from sqlalchemy.ext.asyncio import async_sessionmaker

@asynccontextmanager
async def get_task_session():
    # Utilise l'engine global déjà créé et sur lequel init_db() a créé les tables
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
