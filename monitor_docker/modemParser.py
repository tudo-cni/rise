#!/usr/bin/bin/sudo python3.9
import logging
import re
import numpy as np
import pandas as pd


def parse_nwcfg_txpower(pdata: str, ptype: str = "lte") -> pd.DataFrame:
    """
    +QNWCFG="lte_ulMCS",1,20,4
    """
    ptype = ptype.lower()
    command_str = '"' + ptype + '_tx_pwr",1,'

    pusch = ptype + "_pusch_tx_power"
    pucch = ptype + "_pucch_tx_power"
    srs = ptype + "_srs_tx_power"
    prach = ptype + "_prach_tx_power"

    dataf = pd.DataFrame(np.nan, index=[0], columns=[pusch, pucch, srs, prach])

    if pdata is None or len(pdata) == 0:
        logging.error("Parse TX-Power: Input data is empty")
        return dataf
    if command_str not in pdata:
        logging.error("Parse TX-Power: suspected Input is not in Input String")
        return dataf

    searchstring = '(?<=' + command_str + ')(.*)'
    temp = re.findall(searchstring, pdata)
    if not temp:
        logging.error("Parse TX-Power: Input data is not of suspected format")
        logging.debug(f"{searchstring} could not be found in {pdata}")
        return dataf

    temp = temp[0].split(",")
    if len(temp) != 4:
        logging.error("Parse TX-Power: Input data has not the suspected length")
        logging.debug(temp)
        return dataf
    try:
        dataf[pusch] = float(temp[0])
        dataf[pucch] = float(temp[1])
        dataf[srs] = float(temp[2])
        dataf[prach] = float(temp[3])
        dataf = dataf.mask(dataf > 30, np.nan).mask(dataf < -100, np.nan)
    except Exception:
        logging.error(f"Exception in parsing parse_nwcfg_txpower, values: {temp}")
    return dataf

def parse_nwcfg_txpower_5g(data) -> pd.DataFrame:
    return parse_nwcfg_txpower(data, ptype="nr5g")

def parse_nwcfg_nr5g_pusch(pdata: str):
    """

    """

    command_str = '"nr5g_pusch_data",1,'

    dataf = pd.DataFrame(np.nan, index=[0],
                         columns=["nr_scs", "nr_pusch_ul_mcs", "nr_pusch_mod_type", "nr5g_rb_start", "nr5g_num_rb", "nr5g_tb_size"],
                         dtype=float)

    if pdata is None or len(pdata) == 0:
        logging.error("Parse 5G PUSCH: Input data is empty")
        return dataf
    if command_str not in pdata:
        logging.error(f"Parse 5G PUSCH: Suspected Input is not in Input String: {pdata}")
        return dataf

    searchstring = '(?<=' + command_str + ')(.*)'
    temp = re.findall(searchstring, pdata)
    if not temp:
        logging.error("Parse 5G PUSCH: Input data is not of suspected format")
        return dataf

    temp = temp[0].split(",")
    if len(temp) != 6:
        logging.error("Parse 5G PUSCH: Input data is not of the suspected length")
        return dataf

    for i in range(6):
        try:
            dataf[dataf.columns[i]] = float(temp[i])
        except ValueError as e:
            logging.error(f"Parse 5G PUSCH: Could not Parse {dataf.columns[i]}: {e} \n values: '{temp[i]}'")

    dataf["nr_scs"] = dataf["nr_scs"].replace(to_replace=[0, 1, 2, 3, 4], value=[15, 30, 60, 120, 240])

    return dataf

def parse_qrsrp(qrsrp_strs: str) -> pd.DataFrame:
    """
    example answer: "+QRSRP: -101,-105,-109,-99,LTE"
    can also contain multiple lines:
    ```
        +QRSRP: -93,-88,-32768,-32768,LTE
        +QRSRP: -77,-72,-76,-81,NR5G
        OK```
    """
    # todo: add 5G to columns always: spaltenanzahl gleich halten
    pcolumns = ["prx_rsrp_lte", "drx_rsrp_lte", "rx2_rsrp_lte", "rx3_rsrp_lte", "prx_rsrp_nr", "drx_rsrp_nr",
                "rx2_rsrp_nr", "rx3_rsrp_nr"]
    pdataf = pd.DataFrame([[np.nan] * len(pcolumns)], columns=pcolumns)

    if qrsrp_strs is None or "+QRSRP:" not in qrsrp_strs:
        logging.warning(f"QRSRP measurement failed: {qrsrp_strs}")
        return pdataf

    qrsrp_strs_list = qrsrp_strs[qrsrp_strs.find("+QRSRP:"):].strip("\nOK").split("\n")

    qrsrp_find_regex = re.compile(r'(?<=\+QRSRP: ).*')

    for qrsrp_str in qrsrp_strs_list:
        qrsrp_match = qrsrp_find_regex.search(qrsrp_str)
        if qrsrp_match:
            rsrp_data = qrsrp_match.group().split(",")
            if len(rsrp_data) != 5:
                logging.warning(f"QRSRP: Response too short: {qrsrp_str}")
                continue
            if rsrp_data[4].strip() == "NR5G":
                offset = 4
            else:
                offset = 0

            for ind, val in enumerate(rsrp_data):
                if ind < 4:
                    # try to parse to int
                    rsrp_value = np.nan
                    try:
                        rsrp_value = int(val)
                    except ValueError:
                        # can be nonnumeric, as could be not connected or not able to measure
                        pass
                    if rsrp_value > -44:
                        rsrp_value = np.nan
                    if rsrp_value < -140:
                        rsrp_value = np.nan
                    pdataf[pcolumns[ind + offset]] = rsrp_value
    return pdataf