# ============================================
# OKi CAN Interface (PCAN-USB)
# ============================================

import can
from datetime import datetime

BITRATE = 250000
CHANNEL = "PCAN_USBBUS1"


def init_can():
    """
    Initialize PCAN interface
    """
    bus = can.interface.Bus(
        interface="pcan",
        channel=CHANNEL,
        bitrate=BITRATE
    )
    print("CAN interface initialized.")
    return bus


def read_frame(bus, timeout=1.0):
    """
    Read single CAN frame
    """
    msg = bus.recv(timeout)

    if msg is None:
        return None

    return {
        "timestamp": datetime.now(),
        "arbitration_id": msg.arbitration_id,
        "is_extended_id": msg.is_extended_id,
        "data": list(msg.data)
    }