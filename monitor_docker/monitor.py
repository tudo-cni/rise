import sys
import os.path
import traceback
import socket
import zmq
import serial
import time
import threading
import logging
from enum import Enum
import modemParser
from monitor_settings import MonitorSettings

if sys.version_info >= (3, 7):
    time_ns = time.time_ns
else:
    def time_ns():
        return int(time.time() * 1e9)


class QuectelAtCommand(Enum):
    RSRP = "AT+QRSRP"
    NWCFG_5G_PUSCH_ENABLE = 'AT+QNWCFG="nr5g_pusch_data",1'
    NWCFG_5G_PUSCH = 'AT+QNWCFG="nr5g_pusch_data"'
    NWCFG_NR5G_TXPower_ENABLE = 'AT+QNWCFG="nr5g_tx_pwr",1'
    NWCFG_NR5G_TXPower = 'AT+QNWCFG="nr5g_tx_pwr"'


lock = threading.Lock()

def sendatcommand(pcommand: QuectelAtCommand, pmodem_port: str, ptimeout: float = 1, pprocessAnswer: bool = False, pcooldown=0.02,known_errors=None) -> str:
    """
    :param pcommand: The AT command that should be executed
    :param ptimeout: The Timout time, this function waits for a answer from the modem
    :param pprocessAnswer: Flag specifying, if the command has a answer that needs to be read and returned
    :return: Returns "" or the answer of AT command
    """
    if known_errors is None:
        known_errors = []
    if pcommand is None or pcommand.value == "":
        return ""
    if pmodem_port is None:
        logging.error("Modem Port ist not privided (None)",exc_info=True)
    if not os.path.exists(pmodem_port):
        logging.critical(f"Could not find modem file path '{pmodem_port}'. Is it connected?",exc_info=True)
        return ""

    global lock
    isAquired = lock.acquire(timeout=2)
    if not isAquired:
        logging.error("Serial Lock is locked. Can not send serial command")
        return ""

    try:
        if float(serial.__version__) < 3.5:
            ser = serial.Serial(pmodem_port, 115200, rtscts=True, dsrdtr=True,
                                timeout=0.01)  # timeout seems not to work in previous versions
        else:
            ser = serial.Serial(pmodem_port, 115200, rtscts=True, dsrdtr=True,
                                timeout=ptimeout)  # open serial port
    except serial.serialutil.SerialException as se:
        logging.error(f"Could not open Serial port due to Serial exception: {se}",exc_info=True)
        traceback.print_exc()
        if isAquired:
            lock.release()
        return ""

    pAnswer = ""
    try:
        if ser:
            if not ser.isOpen():
                ser.open()
            # ser.timeout = ptimeout
            ser.reset_input_buffer()
            ser.write((pcommand.value + '\r\n').encode())

            if pprocessAnswer:
                okReceived = False
                pTimeStart = time.time()

                if float(serial.__version__) < 3.5:
                    while (time.time() - pTimeStart < ptimeout and not okReceived):
                        temp = ser.read_until(terminator="OK\r\n".encode('utf-8'))
                        pAnswer = pAnswer + temp.decode()
                        if pAnswer.endswith("OK\r\n"):
                            okReceived = True
                else:
                    while (time.time() - pTimeStart < ptimeout and not okReceived):
                        temp = ser.read_until(expected="OK\r\n".encode('utf-8')) #must be a byte array, otherwise blocks until timeout
                        pAnswer = pAnswer + temp.decode()
                        if pAnswer.endswith("OK\r\n"):
                            okReceived = True
                # while ser.in_waiting or (datetime.now() - pTimeStart).total_seconds() < ptimeout:
                #     temp = ser.read(ser.in_waiting).decode()
                #     pAnswer = pAnswer + temp
                #     time.sleep(pcooldown)
                if not okReceived and not [ele for ele in known_errors if(ele in pAnswer)]:
                    logging.warning("serial timeout '" +pcommand.value + "'\n"+pAnswer )
                pAnswer = pAnswer.replace("OK\r\n", "")
                pAnswer = pAnswer.strip()

            ser.reset_input_buffer()
    except serial.serialutil.SerialException as se:
        logging.error(f"serial exception while executing command:\n{se}")
    except Exception as e:
        logging.error(e)
        logging.error("unknown Error in serial")
    finally:
        ser.close()
        if isAquired:
            lock.release()
        return pAnswer


def send_enable_command(port, command, max_tries=3):
    """
    Sends a set command max. max_tries times until "OK" is returned.
    Some at commands need to be enabled at the start. This may fail in rare cases. So retries are used.
    :param port: AT-Command Port to Use
    :param command: The Enable command to send
    :param max_tries: The maximum number of retries
    :return: Wheter enabling the command was successfull.
    """
    answer = ""
    tries = 0
    while "OK" not in answer and tries < max_tries:
        answer = sendatcommand(command, port, 0.5, True)
        tries = tries + 1
    return not (tries == max_tries)


if __name__ == "__main__":

    mpref = MonitorSettings.from_yaml_file("monitor_pref.yaml")


    hostname = socket.gethostname()
    at_ports = mpref.at_ports
    for i in range(2):
        print(QuectelAtCommand.NWCFG_5G_PUSCH_ENABLE)
        send_enable_command(at_ports[i], QuectelAtCommand.NWCFG_5G_PUSCH_ENABLE)
        send_enable_command(at_ports[i], QuectelAtCommand.NWCFG_NR5G_TXPower_ENABLE)

    tagss = [{"modem_name": name} for name in mpref.modem_names]


    parse_lookup = {QuectelAtCommand.RSRP: modemParser.parse_qrsrp,
                    QuectelAtCommand.NWCFG_5G_PUSCH: modemParser.parse_nwcfg_nr5g_pusch,
                    QuectelAtCommand.NWCFG_NR5G_TXPower: modemParser.parse_nwcfg_txpower_5g}


    # ZMQ Setup
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.bind(f'tcp://*:{mpref.zmq_port}')
    while True:
        for i in range(2):
            buffer = {}
            for at_command, parser in parse_lookup.items():
                result_str = sendatcommand(at_command, at_ports[i], 0.35, True)
                parsed_data = parse_lookup[at_command](result_str)
                data_json = parsed_data.to_dict("records")[0]

            for at_command, metrics in data_json.items() :
                if metrics is not None:
                    pub.send_json(dict(
                        measurement=f'combox_monitor_nrquectel',
                        hostname=hostname,
                        tags={'at_command': at_command, **tagss[i]},
                        time=time_ns(),
                        fields=metrics
                    ))
        time.sleep(0.3)


