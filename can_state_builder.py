# ============================================
# OKi CAN State Builder v1.0
# ============================================

def decode_uint16(b0, b1):
    return b0 | (b1 << 8)


def decode_int16(b0, b1):
    value = decode_uint16(b0, b1)
    if value >= 0x8000:
        value -= 0x10000
    return value


def update_state_from_frame(frame_id, data, state):

    if frame_id == 0x355:
        soc = decode_uint16(data[0], data[1])
        state["Battery"]["SoC"] = float(soc)

    elif frame_id == 0x356:
        voltage = decode_uint16(data[0], data[1]) * 0.01
        current = decode_int16(data[2], data[3]) * 0.1
        temp = decode_uint16(data[4], data[5]) * 0.1

        state["Battery"]["Voltage"] = voltage
        state["Battery"]["Current"] = current
        state["Battery"]["Temperature"] = temp