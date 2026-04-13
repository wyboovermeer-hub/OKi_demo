# ============================================================
# OKi Shelly Listener v3.0
# AC Grid Monitoring Interface
# ============================================================

import threading
import time
from typing import Optional, Dict, Any

import requests


class ShellyListener(threading.Thread):
    """
    Periodically polls a Shelly Pro EM device and updates the OKi state.

    Behaviour when Shelly is offline:
    - Marks AC measurement section as unavailable.
    - Sets a clear 'ShellyStatus' flag in the state.
    - Uses a backoff delay to avoid log spam.
    """

    def __init__(
        self,
        state_manager,
        ip: str = "192.168.1.50",
        poll_interval_ok: float = 2.0,
        poll_interval_offline: float = 10.0,
    ) -> None:
        super().__init__(daemon=True)

        self.sm = state_manager
        self.ip = ip
        self.poll_interval_ok = poll_interval_ok
        self.poll_interval_offline = poll_interval_offline

        self.running = True
        self._consecutive_errors = 0

    # --------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------

    def _build_offline_payload(self) -> Dict[str, Any]:
        """
        State payload when Shelly is unreachable.
        AC values set to None, Shore False, status string set.
        """
        return {
            "AC": {
                "GridVoltage": None,
                "GridCurrent": None,
                "GridPower": None,
                "GridEnergyTotal": None,
                "Shore": False,
                "ShellyStatus": "OFFLINE",
            }
        }

    def _build_online_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Shelly EM JSON fields into OKi AC state structure.
        """
        voltage = data.get("a_voltage")
        current = data.get("a_current")
        power = data.get("a_power")
        energy = data.get("total_act_energy")

        shore = voltage is not None and voltage > 200

        return {
            "AC": {
                "GridVoltage": voltage,
                "GridCurrent": current,
                "GridPower": power,
                "GridEnergyTotal": energy,
                "Shore": shore,
                "ShellyStatus": "ONLINE",
            }
        }

    def _poll_shelly(self) -> Optional[Dict[str, Any]]:
        """
        Perform a single HTTP request to the Shelly device.
        Returns parsed JSON dict on success, or None on any error.
        """
        url = f"http://{self.ip}/rpc/EM.GetStatus?id=0"
        try:
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print("Shelly read error:", e)
            return None

    # --------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------

    def run(self) -> None:
        print("Shelly listener started")

        # Mark offline initially until we have valid data
        self.sm.bulk_update(self._build_offline_payload())

        while self.running:
            data = self._poll_shelly()

            if not self.running:
                break

            if data is None:
                # Shelly unreachable
                self._consecutive_errors += 1
                self.sm.bulk_update(self._build_offline_payload())
                delay = (
                    self.poll_interval_offline
                    if self._consecutive_errors >= 3
                    else self.poll_interval_ok
                )
            else:
                # Shelly reachable
                self._consecutive_errors = 0
                self.sm.bulk_update(self._build_online_payload(data))
                delay = self.poll_interval_ok

            time.sleep(delay)

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    def stop(self) -> None:
        self.running = False
