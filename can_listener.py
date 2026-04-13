# ============================================================
# OKi CAN Listener v2.0
# PCAN-USB Interface
# ============================================================

import can
import threading
from datetime import datetime

from can_state_builder import update_state_from_frame


class CANListener(threading.Thread):

    def __init__(self, state_manager):

        super().__init__(daemon=True)

        self.sm = state_manager
        self.running = True


# ------------------------------------------------------------
# RUN LOOP
# ------------------------------------------------------------

    def run(self):

        try:

            bus = can.interface.Bus(

                interface="pcan",
                channel="PCAN_USBBUS1",
                bitrate=250000

            )

            print("CAN connected")

        except Exception as e:

            print("CAN unavailable:", e)
            return


        while self.running:

            msg = bus.recv(1.0)

            if msg:

                state = self.sm.get()

                update_state_from_frame(

                    msg.arbitration_id,
                    list(msg.data),
                    state

                )

                self.sm.update(

                    "Communication",
                    "LastCANMessage",
                    datetime.utcnow().isoformat()

                )

                self.sm.update(

                    "Communication",
                    "CANHealthy",
                    True

                )


# ------------------------------------------------------------
# STOP
# ------------------------------------------------------------

    def stop(self):

        self.running = False