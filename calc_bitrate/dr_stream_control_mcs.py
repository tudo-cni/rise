import sys
import time
from importlib import import_module

from cal_datarate_pref import CalcDataratePref
import logging
import zmq
import numpy as np
from modem_status import UplinkModemStatus



def get_int_from_zmq(data:dict, fname)->(int | None, bool):
    field = None
    if "fields" in data and fname in data["fields"] and data["fields"][fname] != "" and data["fields"][fname] is not None:
        try:
            field = int(data["fields"][fname])
        except ValueError:
            logging.error(f"Can not parse field {fname}!", exc_info=True)
        if field == -200:
            field = np.nan
        return field, True
    else:
        return field, False

def load_func(dotpath: str):
    """ load function in module.  function is right-most segment """
    module_, func = dotpath.rsplit(".", maxsplit=1)
    m = import_module(module_)
    return getattr(m, func)


def get_dr_margin(mcs_ind):
    # at low mcs, higher chance of data loss
    if mcs_ind < 5:
        return 0.4
    if mcs_ind < 7:
        return 0.1
    return 0.05


class DatarateMCS:

    def zmq_subscriber(self):
        context_in = zmq.Context()
        connect_to = f"tcp://{self.pref.socket_in_url}:{self.pref.socket_in_port}"
        logging.info(f"Connecting to Modem data stream: {connect_to}")
        socket_in = context_in.socket(zmq.SUB)
        socket_in.connect(connect_to)
        socket_in.subscribe("")
        logging.info("Connected")

        return socket_in

    def zmq_publisher(self):
        # Transmit data to Video Encoder
        context = zmq.Context()
        logging.info("Creating ZMQ Publisher…")
        socket = context.socket(zmq.PUB)
        socket.bind(f"tcp://0.0.0.0:{self.pref.socket_out_port}")
        time.sleep(1)  # wait for bind
        return socket

    def __init__(self, pref: CalcDataratePref):
        self.pref = pref

        self.socket_in = self.zmq_subscriber()
        self.socket_out = self.zmq_publisher()

        # create list of modem classes
        self.modem_list = []
        self.possible_cell_datarates = []
        self.cur_cell_datarates = []
        self.sent_cell_datarates = []
        self.modem_update_status = []
        for index, cell in enumerate(pref.cells):
            self.modem_list.append(UplinkModemStatus(cell,debug_prints=index==1))
            self.possible_cell_datarates.append(0.0)
            self.cur_cell_datarates.append(0.0)
            self.sent_cell_datarates.append(0.0)
            self.modem_update_status.append(0)
        self.cur_link = 0

        self.cur_modem = None
        self.cur_modem_ind = None

    def process_zmq_input(self, data):
        temp_bw, inside = get_int_from_zmq(data, "nr_dl_bandwidth")
        if inside:
            self.modem_update_status[self.cur_modem_ind] = 0
            self.cur_modem.update_bandwidth(temp_bw)
        temp_scs, inside = get_int_from_zmq(data, "nr_scs")
        if inside:
            self.modem_update_status[self.cur_modem_ind] = 1
            self.cur_modem.update_scs(temp_scs)

        temp_nprb, inside = get_int_from_zmq(data, "nr5g_num_rb")
        if inside:
            self.modem_update_status[self.cur_modem_ind] = 2
            self.cur_modem.update_nrb(temp_nprb)

        ul_mcs, inside = get_int_from_zmq(data, "nr_pusch_ul_mcs")
        if inside:
            self.modem_update_status[self.cur_modem_ind] = 3
            self.cur_modem.update_ul_mcs(ul_mcs)

        txp, inside = get_int_from_zmq(data, "nr5g_pusch_tx_power")
        if inside:
            self.modem_update_status[self.cur_modem_ind] = 4
            prbs = self.cur_modem.get_rbs()
            if prbs < 10 and txp == 0:
                self.cur_modem.update_txpower(-15 )
            else:
                self.cur_modem.update_txpower(txp)

        else:
            self.modem_update_status[self.cur_modem_ind] = -1

    def get_cur_modem(self, data):
        modem_name = data["tags"]["modem_name"]
        cur_cell_list = [(t, int(i)) for i, t in enumerate(self.modem_list) if t.get_modem_name() == modem_name]
        if len(cur_cell_list) == 1:
            self.cur_modem = cur_cell_list[0][0]
            self.cur_modem_ind = cur_cell_list[0][1]
        elif len(cur_cell_list) > 1:
            logging.fatal(f"Multiple cells fit to name '{modem_name}'")
            sys.exit(1)
        else:
            logging.info("Got Modem data from modem not in config")
            self.cur_modem = None
            self.cur_modem_ind = None

    def loop(self):
        logging.info("Entering MCS loop")
        while True:
            data = self.socket_in.recv_json()
            # START
            # SEMI STATIC Parameters
            #
            self.get_cur_modem(data)
            if self.cur_modem_ind is None or self.cur_modem_ind is None:
                continue
            self.process_zmq_input(data)

            if self.modem_update_status[self.cur_modem_ind] != 4:
                continue

            possible_dr = float(self.cur_modem.calculate_possible_uplink_datarate(self.pref.application_overhead))
            cur_dr = float(self.cur_modem.calculate_current_uplink_datarate(self.pref.application_overhead))
            if possible_dr is not None:
                self.possible_cell_datarates[self.cur_modem_ind] = possible_dr
            if cur_dr is not None:
                self.cur_cell_datarates[self.cur_modem_ind] = cur_dr

            self.print_info_str()


            self.socket_out.send_json(
                {self.cur_modem.get_modem_name(): {"bitrate": self.possible_cell_datarates[self.cur_modem_ind] * 1000}})

            dr_seamless = self.possible_cell_datarates[self.cur_modem_ind]
            if self.cur_modem_ind != self.cur_link:
                # add some hysteresis
                self.sent_cell_datarates[self.cur_modem_ind] = dr_seamless * 0.85
            else:
                self.sent_cell_datarates[self.cur_modem_ind] = dr_seamless

            seamless_str = f"msting nr {self.cur_modem.get_modem_name()} bitrate {self.sent_cell_datarates[self.cur_modem_ind]}"
            self.socket_out.send_string(seamless_str)
            #logging.debug(seamless_str)

            # send out combined data rate for encoder
            comb_dr = load_func(self.pref.send_combined_func)(self.possible_cell_datarates)


            self.socket_out.send_json({"Combined": {"bitrate": comb_dr * 1000.0,
                                                    "modem1": self.possible_cell_datarates[0] * 1000.0, #to allow switch between modes
                                                    "modem2": self.possible_cell_datarates[0] * 1000.0 }}) # to allow switch between modes




    def print_info_str(self):
        mcs_str = f"MCS={self.cur_modem.mcs_predictor.get_prediction():<3.0f}"
        ptx_str = f"Ptx={self.cur_modem.txp_predictor.get_prediction():<3.0f}"
        rb_str = f"Nrb={self.cur_modem.rb_predictor.get_prediction():<3.0f}"
        cur_dr_str = f"ur_dr={self.cur_cell_datarates[self.cur_modem_ind]:<4.1f}"
        pos_dr_str = f"pos_dr={self.possible_cell_datarates[self.cur_modem_ind]:<4.1f}"
        info_str = f"{self.cur_modem.get_modem_name()}: {mcs_str}, {ptx_str}, {rb_str} --> {cur_dr_str}, {pos_dr_str}"
        if self.cur_modem_ind == len(self.pref.cells) - 1:
            info_str = info_str + "\n"
        logging.info(info_str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    ppref = CalcDataratePref.from_yaml_file("calc_datarate_pref.yaml")

    pobj = DatarateMCS(ppref)
    pobj.loop()
