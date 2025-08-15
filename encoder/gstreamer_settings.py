from dataclasses import dataclass, field
from pyexpat import features

from dataclass_wizard import YAMLWizard

@dataclass
class GstreamerSettings(YAMLWizard):
    source_element: str = field(default="v4l2src device=/dev/video0")
    use_file_src: bool = field(default=False)
    file: str = field(default="/video/video.mp4")
    loop_file : bool = field(default=False)

    encoder_settings: str = field(default="")
    initial_bitrate_kbps: int = field(default=10000)

    stream_target: str = field(default="localhost")
    stream_port: int = field(default=1234)


    zmq_host : str = field(default="localhost")#127.0.0.1")
    zmq_port : int = field(default=5555)

    max_bitrate: float = field(default=32000)
    buffer_feedback : bool = field(default=True)
    const_bitrate: bool = field(default=False)

    def __post_init__(self):
        pass
