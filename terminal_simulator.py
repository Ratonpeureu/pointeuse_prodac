"""
Simule 3 employés qui pointent réaliste (arrivée, pause, retour, départ).
Envoie les données TCP au serveur comme une vraie pointeuse.
"""

import asyncio
import socket
from datetime import datetime, timedelta, time
import random

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TerminalSimulator")

EMPLOYES_SIMULES = [
    {
        "nom": "Diallo",
        "prenom": "Mohamed",
        "id_pointeuse": "EMP001",  #  Doit correspondre au ce qui qui a été creer en db comme emp
        "horaire_arrivee": "08:00",
        "horaire_depart": "17:00",
        "heure_pause_deb": "13:00",
        "duree_pause_min": 60,
    },
    {
        "nom": "Ndiaye",
        "prenom": "Fatou",
        "id_pointeuse": "EMP002",
        "horaire_arrivee": "08:30",
        "horaire_depart": "17:30",
        "heure_pause_deb": "13:15",
        "duree_pause_min": 60,
    },
    {
        "nom": "Cisse",
        "prenom": "Amadou",
        "id_pointeuse": "EMP003",
        "horaire_arrivee": "07:45",
        "horaire_depart": "16:45",
        "heure_pause_deb": "12:45",
        "duree_pause_min": 45,
    },
]

class TerminalSimulator:
    """Simule une pointeuse biométrique ZKTeco K14 en CSV"""
    
    def __init__(self, host="localhost", port=9999, format="csv"):
        self.host = host
        self.port = port
        self.format = format
        self.socket = None
        self.running = False
    
    async def connect(self):
        """Établit la connexion TCP"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logger.info(f"✓ Connecté à {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"✗ Connexion échouée: {e}")
            return False
    
    async def disconnect(self):
        """Ferme la connexion"""
        if self.socket:
            try:
                self.socket.close()
                logger.info("✓ Déconnecté")
            except:
                pass
    
    def _build_pointage_csv(self, id_pointeuse: str, timestamp: datetime, action: int) -> str:
        """
        Format ZKTeco K14:
        ID_POINTEUSE,TIMESTAMP,ACTION,STATUT_BADGE,DEVICE_ID
        
        ACTION: 0=arrivée, 1=pause, 2=fin_pause, 3=départ
        STATUT_BADGE: 0=OK, 1=Erreur
        """
        ts = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        device_id = "SIM_K14_001"
        
        action_names = {0: "arrivée", 1: "pause", 2: "fin_pause", 3: "départ"}
        
        line = f"{id_pointeuse},{ts},{action},0,{device_id}"
        logger.info(f"  [{action_names[action]}] {id_pointeuse} @ {ts}")
        return line
    
    async def send_pointage(self, id_pointeuse: str, timestamp: datetime, action: int):
        """Envoie un pointage au serveur"""
        try:
            data = self._build_pointage_csv(id_pointeuse, timestamp, action)
            self.socket.send((data + "\n").encode("utf-8"))
            await asyncio.sleep(0.2)  # Petite pause entre envois
        except Exception as e:
            logger.error(f" Erreur envoi: {e}")
    
    async def simulate_employee_day(self, emp: dict, today: datetime):
        id_ptr = emp["id_pointeuse"]
        
        # ARRIVÉE : horaire prévu ± 0-10 min
        arr_base = datetime.strptime(emp["horaire_arrivee"], "%H:%M").time()
        arr_min_drift = random.randint(-2, 8)  # Peut être en retard
        arr_time = datetime.combine(today.date(), arr_base) + timedelta(minutes=arr_min_drift)
        
        logger.info(f"\n {emp['prenom']} {emp['nom']}")
        await self.send_pointage(id_ptr, arr_time, action=0)
        await asyncio.sleep(1)
        
        #  PAUSE : horaire prévu ± 2 min
        pause_base = datetime.strptime(emp["heure_pause_deb"], "%H:%M").time()
        pause_drift = random.randint(-1, 2)
        pause_time = datetime.combine(today.date(), pause_base) + timedelta(minutes=pause_drift)
        
        await self.send_pointage(id_ptr, pause_time, action=1)
        await asyncio.sleep(1)
        
        # FIN PAUSE : pause_time + durée_pause + ± 1 min
        pause_duration = emp["duree_pause_min"]
        fin_pause_drift = random.randint(-1, 3)
        fin_pause_time = pause_time + timedelta(minutes=pause_duration + fin_pause_drift)
        
        await self.send_pointage(id_ptr, fin_pause_time, action=2)
        await asyncio.sleep(1)
        
        dep_base = datetime.strptime(emp["horaire_depart"], "%H:%M").time()
        dep_drift = random.randint(-5, 15)  # Plus de variation
        dep_time = datetime.combine(today.date(), dep_base) + timedelta(minutes=dep_drift)
        
        await self.send_pointage(id_ptr, dep_time, action=3)
    
    async def run_simulation(self, jour: datetime = None, loop_count=1):
        """
        Lance la simulation pour N jour(s).

        jour: Date à simuler (défaut = aujourd'hui)
        loop_count: Nombre de jours à simuler
        """
        if jour is None:
            jour = datetime.now()
        
        if not await self.connect():
            return
        
        try:
            for day_offset in range(loop_count):
                current_day = jour + timedelta(days=day_offset)
                
                logger.info("\n" + "="*60)
                logger.info(f"  SIMULATION JOURNÉE: {current_day.strftime('%Y-%m-%d %A')}")
                logger.info("="*60)
                
                # Simuler chaque employé
                for emp in EMPLOYES_SIMULES:
                    await self.simulate_employee_day(emp, current_day)
                    await asyncio.sleep(2)  # Pause entre employés
                
                logger.info("\n✓ Journée simulée\n")
                
                if day_offset < loop_count - 1:
                    logger.info("⏳ Pause 5 sec avant la journée suivante...\n")
                    await asyncio.sleep(5)
        
        finally:
            await self.disconnect()


async def main():
    """Point d'entrée"""
    
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         SIMULATEUR DE POINTEUSE BIOMÉTRIQUE               ║
    ║                 ZKTeco K14 Standalone                      ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    print("cheeckeez que le serveur de pointage tourne:")
    print("  → python -m pointage_prodac.main\n")
    
    print("IMPORTANT: Créer d'abord les 3 employés en base de données avec:")
    for emp in EMPLOYES_SIMULES:
        print(f"   - {emp['prenom']} {emp['nom']} (ID pointeuse: {emp['id_pointeuse']})")
    print()
    
    simulator = TerminalSimulator(host="localhost", port=9999)
    
    await simulator.run_simulation(
        jour=datetime.now(),
        loop_count=1  # 1 jour
    )
    
    print("\n✓ Simulation terminée************")
    print("  → Allez voir http://localhost:8000 pour visualiser les pointages")


if __name__ == "__main__":
    asyncio.run(main())