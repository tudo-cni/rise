import logging

# Helper for 5G NR based calculations
import numpy as np
import pandas as pd

# Data from 5G in Bullets

# 5G in Bullets page 186
nr_mcs_table2 = {
    0: (2, 0.117, 0.2344),
    1: (2, 0.188, 0.3770),
    2: (2, 0.301, 0.6016),
    3: (2, 0.438, 0.8770),
    4: (2, 0.588, 1.1758),
    5: (4, 0.369, 1.4766),
    6: (4, 0.424, 1.6953),
    7: (4, 0.479, 1.9141),
    8: (4, 0.540, 2.1602),
    9: (4, 0.602, 2.4063),
    10: (4, 0.643, 2.5703),
    11: (6, 0.455, 2.7305),
    12: (6, 0.505, 3.0293),
    13: (6, 0.554, 3.3223),
    14: (6, 0.602, 3.6094),
    15: (6, 0.650, 3.9023),
    16: (6, 0.702, 4.2129),
    17: (6, 0.754, 4.5234),
    18: (6, 0.803, 4.8164),
    19: (6, 0.853, 5.1152),
    20: (8, 0.667, 5.3320),
    21: (8, 0.694, 5.5547),
    22: (8, 0.736, 5.8906),
    23: (8, 0.778, 6.2266),
    24: (8, 0.821, 6.5703),
    25: (8, 0.864, 6.9141),
    26: (8, 0.895, 7.1602),
    27: (8, 0.926, 7.4063),
    28: (2, np.nan, np.nan),
    29: (2, np.nan, np.nan),
    30: (2, np.nan, np.nan),
    31: (2, np.nan, np.nan)
}

physical_resource_blocks_15khz = {
    5: 25,
    10: 52,
    15: 79,
    20: 106,
    25: 133,
    30: 160,
    40: 216,
    50: 270
}
physical_resource_blocks_30khz = {
    5: 11,
    10: 24,
    15: 38,
    20: 51,
    25: 65,
    30: 78,
    40: 106,
    50: 133,
    60: 162,
    70: 189,
    80: 217,
    90: 245,
    100: 273
}
physical_resource_blocks_60khz = {
    10: 11,
    15: 18,
    20: 24,
    25: 31,
    30: 38,
    40: 51,
    50: 65,
    60: 79,
    80: 107,
    90: 121,
    100: 135
}


def get_subcarrier_spacing(mu_subcarrier):
    return 2 ** mu_subcarrier * 15


def get_mu_from_subcarrier_spacing(sspace):
    return np.log2(sspace / 15)


def get_thermal_noise_power_resource_block(temperature_k, mu_subcarrier_spacing):
    bw_hz = get_subcarrier_spacing(mu_subcarrier_spacing) * 1000
    k_boltzmann = 1.380649e-23
    noise_power_lin = (k_boltzmann * temperature_k * bw_hz)
    return 10 * np.log10(noise_power_lin / 1e-3)


def get_nr_prb(bandwidth_MHz, subcarrier_spacing):
    if bandwidth_MHz is None or np.isnan(bandwidth_MHz):
        return None
    if subcarrier_spacing == 0:
        if bandwidth_MHz not in physical_resource_blocks_15khz:
            return None
        return physical_resource_blocks_15khz[bandwidth_MHz]
    elif subcarrier_spacing == 1:
        if bandwidth_MHz not in physical_resource_blocks_30khz:
            return None
        return physical_resource_blocks_30khz[bandwidth_MHz]
    elif subcarrier_spacing == 2:
        if bandwidth_MHz not in physical_resource_blocks_60khz:
            return None
        return physical_resource_blocks_60khz[bandwidth_MHz]


def nr_mcs_to_mod_order_code_rate_table2(mcs: int):
    if mcs is None or np.isnan(mcs):
        return nr_mcs_table2[0]
    return nr_mcs_table2[mcs]


def get_nr_dl_datarate(J, v_layer, Q_m, f_scale, R, N_prb, t_s, OH):
    if J is None or v_layer is None or Q_m is None or f_scale is None or R is None or N_prb is None or t_s is None or OH is None:
        return np.nan
    if np.isnan(J) or np.isnan(v_layer) or np.isnan(Q_m) or np.isnan(f_scale) or np.isnan(R) or np.isnan(
            N_prb) or np.isnan(t_s) or np.isnan(OH):
        return np.nan
    return 1e-6 * J * (v_layer * Q_m * f_scale * R * np.divide(12 * N_prb, t_s) * (np.subtract(1, OH)))


def get_spectral_efficiency(snr_db):
    snr_lin = dBmTomW(snr_db)
    return np.log2(1 + snr_lin)


def get_mcs_row_by_index(index) -> pd.Series:
    df = pd.DataFrame.from_dict(nr_mcs_table2, orient="index", columns=["q_m", "r", "sp_eff"]).reset_index(drop=False)
    return df.loc[index]


def get_mcs_from_spectral_efficiency(sp_eff) -> pd.Series:
    df = pd.DataFrame.from_dict(nr_mcs_table2, orient="index", columns=["q_m", "r", "sp_eff"]).reset_index(drop=False)

    # more margin for higher mcs
    df["margin"] = 1.04 + 5e-4 * df["index"] ** 2
    df["sp_eff_lim"] = df["sp_eff"] * df["margin"]
    # searchsorted gives the first over sp_eff --> minus 1, assure that is not lower than 0
    matching_index = (np.searchsorted(df["sp_eff_lim"], sp_eff) - 1).clip(0)
    return df.loc[matching_index]


def dBmTomW(dBm):
    return 10 ** (dBm / 10)
    # return np.power(10,np.divide(np.array(dBm).astype(float),10))


def mWTodBm(mW):
    if isinstance(mW, pd.Series) and mW.size == 0:
        return mW
    mW = np.array([mW]).astype(float)
    tmp = np.isclose(mW, 0)
    mW[~tmp] = np.multiply(10, np.log10(mW[~tmp]))
    mW[tmp] = -np.inf
    return mW
