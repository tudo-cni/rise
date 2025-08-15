import logging

from cal_datarate_pref import CalcDataratePref, CellParams
from nr_helper import get_nr_prb, get_spectral_efficiency, get_thermal_noise_power_resource_block, \
    get_mcs_from_spectral_efficiency, get_nr_dl_datarate


def calculate_overhead(is_downlink: bool, frequency_range: int = 1) -> float:
    # see "5G in Bullets" page 83
    if is_downlink and frequency_range == 1:
        return 0.14
    elif not is_downlink and frequency_range == 1:
        return 0.08
    elif is_downlink and frequency_range == 2:
        return 0.18
    elif not is_downlink and frequency_range == 2:
        return 0.10
    return 1.0


def get_ofdm_symbol_duration(mu_subcarrier_spacing: int):
    return 0.001 / (14 * 2 ** mu_subcarrier_spacing)


def get_datarate_based_on_mcs(pref: CellParams, q_mod, coding_rate, n_prb=None, is_downlink=False,
                              app_overhead=0) -> float:
    j = 1
    v_layer = pref.number_of_layers

    debug_string = (f"B={pref.cell_bandwidth}")
    debug_string = debug_string + ", " + f"mod={q_mod:.0f}, crate={coding_rate:.3f}"
    debug_string = debug_string + ", " + f"mu_sub={pref.mu_subcarrier_spacing:.0f}"
    if n_prb is None:
        n_prb = get_nr_prb(pref.cell_bandwidth, pref.mu_subcarrier_spacing)
    if n_prb is None:
        logging.error("Number of Resource Blocks is None. Setting it to 1 to not crash.")
        n_prb = 1
    if n_prb > 20:
        n_prb = 45 #Amarisoft does not schedule more than 45
    debug_string = debug_string + ", " + f"NPRB={n_prb}"
    t_s = get_ofdm_symbol_duration(pref.mu_subcarrier_spacing)
    overhead = calculate_overhead(is_downlink=is_downlink, frequency_range=1)
    f_scale = pref.scaling_factor

    #logging.debug(debug_string)
    data_rate_mbits = get_nr_dl_datarate(j, v_layer, q_mod, f_scale, coding_rate, n_prb, t_s, overhead)

    data_rate_mbits = data_rate_mbits * (1 - app_overhead)

    data_rate_mbits = data_rate_mbits * pref.own_utilization_factor

    factor = pref.downlink_percentage
    if not is_downlink:
        factor = 1 - factor
    data_rate_mbits = data_rate_mbits * factor

    return data_rate_mbits
