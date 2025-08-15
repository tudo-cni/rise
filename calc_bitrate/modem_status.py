import logging
from datetime import timedelta
import numpy as np
from dataclass_wizard.wizard_cli.schema import possible_types_for_string_value

from cal_datarate_pref import CellParams
from calc_datarate import get_datarate_based_on_mcs
from linear_state_predictor import LinearStatePredictor
from nr_helper import get_nr_prb, nr_mcs_to_mod_order_code_rate_table2, get_spectral_efficiency, \
    get_mcs_from_spectral_efficiency, nr_mcs_table2, get_mu_from_subcarrier_spacing, get_mcs_row_by_index


class UplinkModemStatus:

    def __init__(self, cell_params: CellParams,debug_prints=False):
        self.cell_params = cell_params
        self.mcs_predictor = LinearStatePredictor(past_lookup_time=timedelta(seconds=4.5), min_val=0, max_val=cell_params.max_mcs,
                                           enable_log=debug_prints)


        self.rb_predictor = LinearStatePredictor(past_lookup_time=timedelta(seconds=2.1), min_val=0, max_val=self.get_max_rbs(),
                                           enable_log=False)

        self.txp_predictor = LinearStatePredictor(past_lookup_time=timedelta(seconds=1.5), min_val=-20,
                                                 max_val=self.cell_params.max_tx_power)

        self.possible_dr_predictor = LinearStatePredictor(past_lookup_time=timedelta(seconds=5), min_val=0,
                                                 max_val=None)
        self.current_dr_predictor = LinearStatePredictor(past_lookup_time=timedelta(seconds=2), min_val=0,
                                                          max_val=None)
        self.falling_mcs = False
        self.falling_mcs_cnt = 0
        self.delta_mcs = 0

    def get_modem_name(self):
        return self.cell_params.measurement_modem_tag

    def update_scs(self, scs):
        if scs is None:
            logging.warning("SCS is None. Not accepted.")
            return
        # test if bw and scs fit together
        bw = self.cell_params.cell_bandwidth
        p_mu = get_mu_from_subcarrier_spacing(scs)
        possible_prbs = get_nr_prb(bw, p_mu)
        if possible_prbs is None:
            logging.error(f"BW and SCS Combination unknown: B={bw}, scs={scs}. Keeping old.")
            return
        self.cell_params.mu_subcarrier_spacing = p_mu


    def update_bandwidth(self, bw):
        if bw is None:
            logging.warning("Bandwidth is None. Not accepted")
            return
        if bw > 900:
            bw = bw / 1000.0
        self.cell_params.cell_bandwidth = bw
        # update predictor
        self.rb_predictor.set_max_val(self.get_max_rbs())


    def update_ul_mcs(self, mcs):
        if mcs is None:
            return
        if mcs > 27 or mcs < 0:
            if not (27 < mcs < 31): # retransmissions
                logging.warning(f"Invalid mcs value: {mcs}. Set to 0")
            mcs = 0
        new_mcs = self.mcs_predictor.get_prediction_new_value(mcs)
        self.delta_mcs = mcs - new_mcs
        if self.delta_mcs >= 0:
            if not self.falling_mcs:
                logging.info("\n\nFalling mcs\n\n")
            self.falling_mcs = True
        else:
            self.falling_mcs_cnt = self.falling_mcs_cnt + 1
            if self.falling_mcs_cnt > 10:
                self.falling_mcs = False
                self.falling_mcs_cnt = 0
                logging.info("\n\n \t\t\trising mcs\n")

    def update_txpower(self, txp):
        self.txp_predictor.get_prediction_new_value(txp)

    def update_nrb(self, nrb):
        self.rb_predictor.get_prediction_new_value(nrb)

    def get_rbs(self)->int|None:
        rbs= self.rb_predictor.get_prediction()
        if rbs is None:
            return None
        return np.round(rbs)

    def get_max_rbs(self) -> int:
        """
        :return: The number of Resource Blocks in the current cell based on the bandwidth and scs
        """
        rbs =  get_nr_prb(self.cell_params.cell_bandwidth, self.cell_params.mu_subcarrier_spacing)
        if rbs is None:
            return 1
        if rbs > 45: #amarisoft does never schedule more than 45 RBs in our configuration
            rbs = 45
        return rbs

    def get_txpower(self) -> int:
        return self.txp_predictor.get_prediction()

    def get_mcs(self) -> int:
        pmcs = self.mcs_predictor.get_prediction()
        if self.falling_mcs:
            pmcs = pmcs - 2.5 - self.delta_mcs
            if pmcs < 0:
                pmcs = 0
        pmcs =  np.floor(pmcs)
        return pmcs

    def get_mcs_table_row(self):
        return nr_mcs_to_mod_order_code_rate_table2(self.get_mcs())

    def calculate_possible_uplink_datarate(self, app_overhead) -> float:
        """
        Returns the maximum possible data rate in the current cell at the current channel conditions, if
        being the only user.
        :param app_overhead: Overhead fraction of the application, e.g. IP + UDP + RTP Overheads
        :return: Possible data rate in Mbit/s
        """
        current_dr = self.current_dr_predictor.get_prediction()

        mcs_table_entry = self.get_mcs_table_row()

        rbs = self.get_rbs()
        if rbs == 0 or rbs is None:
            logging.warning("No. Resource Blocks is 0")
            return self.possible_dr_predictor.get_prediction_new_value(0)

        # assume maximum tx power and maximum available resource blocks --> estimate MCS --> calculate Datarate

        max_rbs = self.get_max_rbs()

        if max_rbs is None:
            logging.error("Maximum possible RBs is 'None'")
            max_rbs = 0

        temp_tx_power = self.get_txpower()
        power_headroom_db = self.cell_params.max_tx_power - temp_tx_power
        sp_eff = mcs_table_entry[2]
        ul_snr_lin = 2 ** sp_eff - 1
        ul_snr = 20 * np.log10(ul_snr_lin)

        if max_rbs < rbs:
            logging.warning("Maximum RBs is smaller than current RBs")
            prb_diff_db = 0
        else:
            prb_diff_db = 20 * np.log10(max_rbs / rbs)

        possible_ul_snr = ul_snr + power_headroom_db - prb_diff_db
        sp_eff_possible = get_spectral_efficiency(possible_ul_snr)
        if sp_eff_possible < nr_mcs_table2[0][2]:
            return self.possible_dr_predictor.get_prediction_new_value(current_dr)
            # if all prbs would be used --> even lowest mcs would not be enough. Possible improvement: Calculate maximum possible number of rbs
        mcs_possible = get_mcs_from_spectral_efficiency(sp_eff_possible)

        if mcs_possible["index"] > self.cell_params.max_mcs:
            mcs_possible = get_mcs_row_by_index(self.cell_params.max_mcs)

        mcs_table_possible = nr_mcs_to_mod_order_code_rate_table2(mcs_possible["index"])
        dr = get_datarate_based_on_mcs(self.cell_params, mcs_table_possible[0], mcs_table_possible[1], max_rbs,
                                       is_downlink=False, app_overhead=app_overhead)

        # add some margin depending on how large the difference between max. and current values is
        headroom_at_30_dB = 0.85
        a = (headroom_at_30_dB-1)/(30**3)
        headroom = np.clip(a*prb_diff_db**3+1, a_min=0.6, a_max=1.0)

        dr = dr * headroom
        dr = dr * (1-self.cell_params.correction_factor)

        possible_dr = self.possible_dr_predictor.get_prediction_new_value(dr)

        if current_dr > possible_dr:
            return current_dr
        return possible_dr

    def calculate_current_uplink_datarate(self, app_overhead) -> float:
        """
               Returns the current data rate of the modem.
               :param app_overhead: Overhead fraction of the application, e.g. IP + UDP + RTP Overheads
               :return: Possible data rate in Mbit/s
               """
        mcs_table_entry = self.get_mcs_table_row()
        dr = get_datarate_based_on_mcs(self.cell_params, mcs_table_entry[0], mcs_table_entry[1], self.get_rbs(),
                                       is_downlink=False, app_overhead=app_overhead)
        return self.current_dr_predictor.get_prediction_new_value(dr)
