from dataclasses import dataclass, field
from dataclass_wizard import YAMLWizard


@dataclass
class CellParams(YAMLWizard):
    measurement_modem_tag: str = field(default="modem")

    cell_bandwidth: int = field(default=100) # Initially used cell bandwidth [MHz] if no measurement from modem is there
    number_of_layers: int = field(default=1)
    mu_subcarrier_spacing: int = field(default=1) #0,1 --> 15, 30, ...kHz Subcarrier spacing. Initial value, overwritten by measured value
    scaling_factor: float = field(default=1.0)
    downlink_percentage: float = field(default=0.7)
    own_utilization_factor: float = field(default=1)
    correction_factor: float = field(default=0)
    max_tx_power: int = field(default=3) # max possible ul tx power of modem (may be restricted by cell)
    max_mcs: int = field(default=28)

@dataclass
class CalcDataratePref(YAMLWizard):
    application_overhead: float = field(default=0)

    socket_in_port : int = field(default=2345)
    socket_out_port: int = field(default=5555)
    socket_in_url : str = field(default="localhost")
    cell_params: CellParams = field(default_factory=lambda : CellParams(measurement_modem_tag="default"))

    cells: list[CellParams] = field(default_factory=lambda:{"cell1":CellParams(measurement_modem_tag="modem")} )
    send_combined_func: str = field(default_factory=lambda: "numpy.max")


    def __post_init__(self):
        pass
