# tests/test_pointage.py
"""
Tests complets du système de pointage biométrique.
Exécution : pytest tests/test_pointage.py -v

Prérequis : pip install pytest-asyncio httpx httpx_ws sqlalchemy aiosqlite
"""

import os
import sys
from datetime import date, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import patch, AsyncMock

import pytest
import httpx_ws  # <-- IMPORTANT pour activer websocket_connect sur AsyncClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

# ── Fix Python 3.13 + SQLAlchemy < 2.0.36 ──────────────────────────
import sqlalchemy.util.langhelpers as _langhelpers
if not hasattr(_langhelpers.TypingOnly, '__init_subclass__'):
    def _patched_init_subclass(cls, *args, **kwargs):
        return
    _langhelpers.TypingOnly.__init_subclass__ = classmethod(_patched_init_subclass)
# ─────────────────────────────────────────────────────────────────────

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

os.environ["TESTING"] = "1"
os.environ["TERMINAL_FORMAT"] = "csv"
os.environ["PAUSE_MODE"] = "terminal"
os.environ["TERMINAL_HOST"] = "0.0.0.0"
os.environ["TERMINAL_PORT"] = "9999"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["LOG_OUTPUT"] = "console"

# Import des modules après avoir forcé la config
from pointage_prodac.config_pointage import config, PointageConfigManager
from pointage_prodac.models import (
    get_db_path, init_db, get_task_session,
    Employe, Pointage, PlanningHebdomadaire, PlanningMensuel,
    gen_id, async_engine as original_engine
)
from pointage_prodac.main import app
from pointage_prodac.terminal_listener import TerminalDataParser, PointageEvent
from pointage_prodac.pointage import PointageDispatcher
from pointage_prodac.terminal_model import (
    TerminalModel, TERMINAL_MODELS, get_terminal_model, list_all_models,
    get_terminal_env_config
)
from pointage_prodac.utils_planning import (
    get_planning_actif, suivi_mensuel_employe, suivi_semaine_employe,
    suivi_jour_tous_employes
)

# ══════════════════════════════════════════════════════════════════════
# Fixtures avec UN SEUL ENGINE PARTAGÉ (test_engine)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("db")
    return str(db_dir / "test.db")

@pytest.fixture(scope="session")
def test_db_url(test_db_path):
    return f"sqlite+aiosqlite:///{test_db_path}"

@pytest.fixture(scope="session")
def test_engine(test_db_url):
    engine = create_async_engine(test_db_url, echo=False, poolclass=NullPool)
    return engine

@pytest.fixture(scope="session", autouse=True)
async def _prepare_db(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await test_engine.dispose()

@pytest.fixture
async def async_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
            await session.rollback()
        finally:
            await session.close()


@pytest.fixture
async def async_client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    import pointage_prodac.models as models_mod
    original_engine = models_mod.async_engine
    models_mod.async_engine = test_engine   # redirige tous les appels DB vers la base de test

    async def override_get_task_session():
        async with test_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_task_session] = override_get_task_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Nettoyage après le test
    models_mod.async_engine = original_engine
    app.dependency_overrides.clear()
# ══════════════════════════════════════════════════════════════════════
# Tests (tous conservés)
# ══════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_default_config(self):
        assert config.terminal_data.format == "csv"
        assert config.pause.mode == "terminal"
        assert config.network.port == 9999
        assert config.log.level == "DEBUG"

    def test_env_override(self):
        os.environ["PAUSE_MODE"] = "hybrid"
        os.environ["TERMINAL_PORT"] = "8888"
        cfg = PointageConfigManager()
        assert cfg.pause.mode == "hybrid"
        assert cfg.network.port == 8888
        os.environ["PAUSE_MODE"] = "terminal"
        os.environ["TERMINAL_PORT"] = "9999"

class TestTerminalModels:
    def test_list_all_models(self):
        models = list_all_models()
        assert len(models) >= 8
        assert "zkteco_k14" in models

    def test_get_model_valid(self):
        model = get_terminal_model("zkteco_k14")
        assert model is not None
        assert model.name == "ZKTeco K14 Standalone Time Attendance Terminal"
        assert model.port == 23

    def test_get_model_invalid(self):
        assert get_terminal_model("nonexistent") is None

    def test_model_to_dict(self):
        model = get_terminal_model("zkteco_k14")
        d = model.to_dict()
        assert d["data_format"] == "csv"
        assert d["field_mapping"]["id_pointeuse"] == 0

    def test_to_env_config(self):
        env = get_terminal_env_config("zkteco_k14")
        assert env["TERMINAL_FORMAT"] == "csv"
        assert env["TERMINAL_PORT"] == "23"

    @pytest.mark.asyncio
    async def test_list_models_api(self, async_client):
        resp = await async_client.get("/configurator/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_get_model_details_api(self, async_client):
        resp = await async_client.get("/configurator/models/zkteco_k14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"]["name"].startswith("ZKTeco")

    @pytest.mark.asyncio
    async def test_preview_configuration_api(self, async_client):
        resp = await async_client.get("/configurator/models/zkteco_k14/preview")
        assert resp.status_code == 200
        data = resp.json()
        assert "env_content" in data
        assert "TERMINAL_FORMAT=csv" in data["env_content"]

    @pytest.mark.asyncio
    async def test_apply_configuration_api(self, async_client):
        with patch("builtins.open") as mock_open:
            resp = await async_client.post("/configurator/models/zkteco_k14/apply")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_search_terminal(self, async_client):
        resp = await async_client.get("/configurator/search?query=K14")
        assert resp.status_code == 200
        data = resp.json()
        assert any("k14" in r["key"].lower() for r in data["results"])

    @pytest.mark.asyncio
    async def test_by_manufacturer(self, async_client):
        resp = await async_client.get("/configurator/by-manufacturer")
        assert resp.status_code == 200
        data = resp.json()
        assert "ZKTeco" in data["manufacturers"]

class TestTerminalDataParser:
    def test_csv_parsing_valid_arrivee(self):
        line = "12345,2026-06-18 08:30:15,0,0,K14001,extra"
        event = TerminalDataParser.parse(line)
        assert event is not None
        assert event.id_pointeuse == "12345"
        assert event.action == 0
        assert event.action_name == "arrivee"
        assert event.timestamp == datetime(2026, 6, 18, 8, 30, 15)

    def test_csv_parsing_pause(self):
        line = "EMP002,2026-06-18 13:15:00,1,0,SIM_K14_001,extra"
        event = TerminalDataParser.parse(line)
        assert event.action_name == "pause"

    def test_csv_parsing_depart(self):
        line = "EMP003,2026-06-18 17:45:00,3,0,SIM_K14_001,extra"
        event = TerminalDataParser.parse(line)
        assert event.action_name == "depart"

    def test_csv_parsing_incomplete_line(self):
        line = "12345,2026-06-18 08:30:15,0"
        event = TerminalDataParser.parse(line)
        assert event is None

    def test_csv_parsing_wrong_timestamp(self):
        line = "12345,invalid,0,0,K14001,extra"
        event = TerminalDataParser.parse(line)
        assert event is None

    def test_json_parsing_valid(self):
        # Sauvegarde de l'état initial
        old_format = TerminalDataParser.CONFIG.format
        TerminalDataParser.CONFIG.format = 'json'
        try:
            raw = '{"id_pointeuse":"12345","timestamp":"2026-06-18T08:30:15","action":0,"status":"0"}'
            event = TerminalDataParser.parse(raw)
            assert event is not None
            assert event.id_pointeuse == "12345"
        finally:
            TerminalDataParser.CONFIG.format = old_format

    def test_json_parsing_missing_field(self):
        old_format = TerminalDataParser.CONFIG.format
        TerminalDataParser.CONFIG.format = 'json'
        try:
            raw = '{"personId":"12345","createTime":"2026-06-18T08:30:15"}'
            event = TerminalDataParser.parse(raw)
            assert event is None
        finally:
            TerminalDataParser.CONFIG.format = old_format

class TestPointageDispatcher:
    @pytest.fixture
    def dispatcher(self):
        return PointageDispatcher()

    @pytest.fixture
    def sample_employee(self):
        return {
            "id": "emp-123",
            "nom": "Diallo",
            "prenom": "Mohamed",
            "id_pointeuse": "EMP001",
        }

    @pytest.fixture
    def sample_event_arrivee(self):
        return PointageEvent(
            id_pointeuse="EMP001",
            timestamp=datetime(2026, 6, 18, 8, 30),
            action=0,
            action_name="arrivee",
            statut_badge=0,
            extra_data={},
            received_at=datetime(2026, 6, 18, 8, 30, 1)
        )

    @pytest.fixture
    def sample_event_pause(self):
        return PointageEvent(
            id_pointeuse="EMP001",
            timestamp=datetime(2026, 6, 18, 13, 15),
            action=1,
            action_name="pause",
            statut_badge=0,
            extra_data={},
            received_at=datetime(2026, 6, 18, 13, 15, 1)
        )

    @pytest.mark.asyncio
    async def test_handle_arrivee_first_time(self, dispatcher, sample_employee, sample_event_arrivee):
        with patch.object(dispatcher, '_find_employe', return_value=sample_employee), \
             patch.object(dispatcher, '_load_today_pointage', return_value=None), \
             patch('pointage_prodac.pointage._persist_pointage', new_callable=AsyncMock):
            result = await dispatcher.handle_terminal_event(sample_event_arrivee)
        assert result["ok"] is True
        assert result["action"] == "arrivee"
        assert result["statut"] == "travail"

    @pytest.mark.asyncio
    async def test_handle_arrivee_rebadge_ignored(self, dispatcher, sample_employee, sample_event_arrivee):
        current_ptg = {
            "heure_arrivee": "08:29",
            "statut": "travail",
            "_received_at": datetime(2026, 6, 18, 8, 29)
        }
        with patch.object(dispatcher, '_find_employe', return_value=sample_employee), \
             patch.object(dispatcher, '_load_today_pointage', return_value=current_ptg):
            result = await dispatcher.handle_terminal_event(sample_event_arrivee)
        assert result.get("ignored") is True

    @pytest.mark.asyncio
    async def test_handle_pause_terminal_mode(self, dispatcher, sample_employee, sample_event_pause):
        current_ptg = {"heure_arrivee": "08:30", "statut": "travail"}
        with patch.object(dispatcher, '_find_employe', return_value=sample_employee), \
             patch.object(dispatcher, '_load_today_pointage', return_value=current_ptg), \
             patch('pointage_prodac.pointage._persist_pointage', new_callable=AsyncMock):
            result = await dispatcher.handle_terminal_event(sample_event_pause)
        assert result["statut"] == "pause"

    @pytest.mark.asyncio
    async def test_handle_pause_system_mode(self, dispatcher, sample_employee, sample_event_pause):
        dispatcher.pause_cfg.mode = "system"
        current_ptg = {"heure_arrivee": "08:30", "statut": "travail"}
        with patch.object(dispatcher, '_find_employe', return_value=sample_employee), \
             patch.object(dispatcher, '_load_today_pointage', return_value=current_ptg):
            result = await dispatcher.handle_terminal_event(sample_event_pause)
        assert result.get("ignored") is True

    @pytest.mark.asyncio
    async def test_employee_not_found(self, dispatcher, sample_event_arrivee):
        with patch.object(dispatcher, '_find_employe', return_value=None):
            result = await dispatcher.handle_terminal_event(sample_event_arrivee)
        assert result["ok"] is False
        assert "non trouv" in result["error"]

class TestPlanning:
    @pytest.mark.asyncio
    async def test_get_planning_actif_none(self, async_session):
        plan, source = await get_planning_actif(async_session, "inexistant", 2026, 6)
        assert plan is None
        assert source == "aucun"

    @pytest.mark.asyncio
    async def test_planning_from_employee_default(self, async_session):
        emp = Employe(
            id=gen_id(),
            id_pointeuse="EMP001",
            nom="Test",
            prenom="User",
            heure_arrivee_prevue="09:00",
            heure_depart_prevue="18:00",
            duree_pause_min=45,
            jours_off="Sam, Dim"
        )
        async_session.add(emp)
        await async_session.commit()

        plan, source = await get_planning_actif(async_session, emp.id, 2026, 6)
        assert source == "employe"
        assert plan.lundi_debut == "09:00"
        assert plan.lundi_fin == "18:00"
        assert "45min" in plan.lundi_pause
        assert plan.samedi_debut == "OFF"

    @pytest.mark.asyncio
    async def test_planning_mensuel_override(self, async_session):
        emp_id = gen_id()
        emp = Employe(id=emp_id, id_pointeuse="EMP002", nom="Doe", prenom="John")
        async_session.add(emp)
        await async_session.commit()

        hebdo = PlanningHebdomadaire(
            employe_id=emp_id, matricule="12345678",
            lundi_debut="08:00", lundi_fin="17:00"
        )
        async_session.add(hebdo)
        await async_session.commit()

        mensuel = PlanningMensuel(
            employe_id=emp_id, matricule="12345678",
            annee=2026, mois=6,
            lundi_debut="10:00", lundi_fin="19:00"
        )
        async_session.add(mensuel)
        await async_session.commit()

        plan, source = await get_planning_actif(async_session, emp_id, 2026, 6)
        assert source == "mensuel"
        assert plan.lundi_debut == "10:00"

    @pytest.mark.asyncio
    async def test_suivi_jour_tous_employes(self, async_client, async_session):
        emp = Employe(
            id=gen_id(),
            id_pointeuse="EMP005",
            nom="Kane",
            prenom="Aminata",
            heure_arrivee_prevue="08:00",
            heure_depart_prevue="17:00"
        )
        async_session.add(emp)
        await async_session.commit()

        today = date.today().isoformat()
        ptg = Pointage(employe_id=emp.id, date_jour=today, heure_arrivee="08:15", statut="travail")
        async_session.add(ptg)
        await async_session.commit()

        response = await async_client.get(f"/suivi/jour?date_str={today}")
        assert response.status_code == 200
        data = response.json()
        assert any(e["employe_id"] == emp.id for e in data["employes"])

    @pytest.mark.asyncio
    async def test_suivi_semaine_employe(self, async_client, async_session):
        emp = Employe(
            id=gen_id(),
            id_pointeuse="EMP010",
            nom="Fall",
            prenom="Ibrahima",
            heure_arrivee_prevue="09:00",
            heure_depart_prevue="18:00"
        )
        async_session.add(emp)
        await async_session.commit()
        today = date.today()
        lundi = today - timedelta(days=today.weekday())
        resp = await async_client.get(f"/suivi/employe/{emp.id}/semaine?date_ref={lundi.isoformat()}")
        assert resp.status_code == 200
        assert resp.json()["employe_id"] == emp.id

    @pytest.mark.asyncio
    async def test_suivi_mensuel_employe(self, async_client, async_session):
        emp = Employe(id=gen_id(), id_pointeuse="EMP020", nom="Sow", prenom="Mariama")
        async_session.add(emp)
        await async_session.commit()
        today = date.today()
        resp = await async_client.get(f"/suivi/employe/{emp.id}/mois?annee={today.year}&mois={today.month}")
        assert resp.status_code == 200
        assert resp.json()["mois"] == today.month

class TestAdminAPI:
    @pytest.mark.asyncio
    async def test_enregistrer_employe(self, async_client):
        payload = {
            "id_pointeuse": "EMP050",
            "prenom": "Awa",
            "nom": "Diop",
            "poste": "Comptable",
            "email": "awa@example.com",
            "heure_arrivee_prevue": "08:30",
            "heure_depart_prevue": "17:30"
        }
        resp = await async_client.post("/admin/employes/enregistrer", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["employe"]["prenom"] == "Awa"

    @pytest.mark.asyncio
    async def test_enregistrer_employe_doublon(self, async_client):
        payload = {"id_pointeuse": "EMP100", "prenom": "Dupont", "nom": "Jean"}
        await async_client.post("/admin/employes/enregistrer", json=payload)
        resp = await async_client.post("/admin/employes/enregistrer", json=payload)
        assert resp.status_code == 400
        assert "déjà utilisé" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_lister_employes(self, async_client):
        for i in range(3):
            await async_client.post("/admin/employes/enregistrer", json={
                "id_pointeuse": f"EMP200{i}",
                "prenom": f"User{i}",
                "nom": f"Test{i}"
            })
        resp = await async_client.get("/admin/employes/liste")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 3

    @pytest.mark.asyncio
    async def test_get_employe_details(self, async_client):
        create = await async_client.post("/admin/employes/enregistrer", json={
            "id_pointeuse": "EMP300", "prenom": "Fatou", "nom": "Ndiaye"
        })
        emp_id = create.json()["employe"]["id"]
        resp = await async_client.get(f"/admin/employes/{emp_id}")
        assert resp.json()["prenom"] == "Fatou"

    @pytest.mark.asyncio
    async def test_modifier_employe(self, async_client):
        create = await async_client.post("/admin/employes/enregistrer", json={
            "id_pointeuse": "EMP400", "prenom": "Old", "nom": "Name"
        })
        emp_id = create.json()["employe"]["id"]
        await async_client.put(f"/admin/employes/{emp_id}", json={
            "id_pointeuse": "EMP400",
            "prenom": "New",
            "nom": "Name",
            "poste": "Dev"
        })
        detail = await async_client.get(f"/admin/employes/{emp_id}")
        assert detail.json()["prenom"] == "New"

    @pytest.mark.asyncio
    async def test_supprimer_employe(self, async_client):
        create = await async_client.post("/admin/employes/enregistrer", json={
            "id_pointeuse": "EMP500", "prenom": "ToDelete", "nom": "User"
        })
        emp_id = create.json()["employe"]["id"]
        await async_client.delete(f"/admin/employes/{emp_id}")
        detail = await async_client.get(f"/admin/employes/{emp_id}")
        assert detail.json()["actif"] == False

    @pytest.mark.asyncio
    async def test_sync_status(self, async_client):
        resp = await async_client.get("/admin/sync-status")
        assert resp.status_code == 200
        assert "total_employes" in resp.json()

    @pytest.mark.asyncio
    async def test_admin_page_html(self, async_client):
        resp = await async_client.get("/admin")
        assert "text/html" in resp.headers["content-type"]

class TestGeneralAPI:
    @pytest.mark.asyncio
    async def test_health(self, async_client):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_config(self, async_client):
        resp = await async_client.get("/config")
        assert resp.status_code == 200
        assert "terminal_format" in resp.json()

    @pytest.mark.asyncio
    async def test_dashboard(self, async_client):
        resp = await async_client.get("/")
        assert resp.status_code == 200
        assert "Suivi Pointages" in resp.text

    ## iDEALEMENT TESTE EN REEL###
    #La j'ignore 
    @pytest.mark.asyncio
    async def test_websocket_pointages(self, async_client):
        if not hasattr(async_client, "websocket_connect"):
            pytest.skip("httpx_ws non disponible (version incompatible ?)")
        async with async_client.websocket_connect("/ws/pointages") as ws:
            assert ws.open

class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_pointage_flow(self, async_client, async_session):
        create = await async_client.post("/admin/employes/enregistrer", json={
            "id_pointeuse": "SIM001",
            "prenom": "Simulation",
            "nom": "Test",
            "heure_arrivee_prevue": "08:00",
            "heure_depart_prevue": "17:00"
        })
        emp_id = create.json()["employe"]["id"]

        from pointage_prodac.utils_planning import db_upsert_pointage
        ptg_data = {
            "employe_id": emp_id,
            "date_jour": "2026-06-18",
            "heure_arrivee": "08:05",
            "statut": "travail"
        }
        await db_upsert_pointage(ptg_data, session=async_session)

        resp = await async_client.get("/suivi/jour?date_str=2026-06-18")
        assert resp.status_code == 200
        data = resp.json()
        emp_entry = next(e for e in data["employes"] if e["employe_id"] == emp_id)
        assert emp_entry["statut"] == "travail"
        assert emp_entry["heure_arrivee"] == "08:05"