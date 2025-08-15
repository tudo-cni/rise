import logging
import sys
from json import JSONDecodeError
from threading import Thread, Lock
import os
import time
import gi
import numpy as np
import zmq
import signal
from gstreamer_settings import GstreamerSettings
import time
import threading
import functools


def debug_log_function(func):
    """Decorator that logs the function name and timestamp at start and end of execution."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        logging.debug(f"Starting function '{func.__name__}' at {start_time}")

        result = func(*args, **kwargs)

        end_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        logging.debug(f"Ending function '{func.__name__}' at {end_time}")

        return result

    return wrapper



gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")

from gi.repository import Gst, GLib, GstApp


class AdaptiveStreamer:
    old_queue_time = 0
    bufferstate_data_lock = Lock()
    queue_points = []
    bitrate_points = []

    queue_drops = []
    queue_drops_lock = Lock()

    queue_drops_cnt = 0
    queue_drops_cnt_lock = Lock()
    queue_drops_last_report = time.time()

    exit_influx = False

    @debug_log_function
    def on_overrun(self, queue):
        logging.debug("on_overrun")
        with self.queue_drops_cnt_lock:
            self.queue_drops_cnt = self.queue_drops_cnt + 1
        logging.debug("end on_overrun")

    @debug_log_function
    def build_gstreamer_pipeline(self):
        logging.debug("Building gstreamer pipeline")
        mode = 264
        source_element = gpref.source_element
        if gpref.use_file_src:
            source_element = f"filesrc location={gpref.file}"
        if gpref.loop_file:
            logging.warning("Looping can only be done on files without an end written into them! (see Readme)")
            source_element = f"multifilesrc location={gpref.file} loop=true"
        if gpref.use_file_src:
            source_element = f"{source_element} ! decodebin ! videorate ! video/x-raw,framerate=60/1 ! identity sync=true"  # make file source play in realtime only (virtual live source) --> to be able to work with leaky ques
        else:
            source_element = f"{source_element}"
        if mode == 265:
            source_element = f"{source_element} ! videoconvert"



        encoder = f"x{mode}enc"

        encoder = encoder + f" {gpref.encoder_settings} name=myenc"
        if mode==264:
            filesink = f"mp4mux ! filesink location=/video/original_encoded.mp4"
        else:
            filesink = f"mpegtsmux ! filesink location=/video/original_encoded.mp4"

        myqueue = f"queue max-size-time={1000*1000*1000}"
        # Drop too old packets to not block stream.
        myqueue2 = f"queue leaky=downstream max-size-time={250 * 1000 * 1000} name=myqueue"
        save_to_file=False
        save_part=""
        if save_to_file:
            save_part = " ! tee name=t t. ! {myqueue} ! {filesink} t."
        launch_str = ""

        logging.info("Transport: UDP")

        port = gpref.stream_port
        # udp
        udp_sink = f"rtph{mode}pay mtu=1350 ! udpsink host={gpref.stream_target} port={port} buffer-size=12500 sync=true name=gs_sink"
        launch_str = f"{source_element} ! {encoder} {save_part} ! {myqueue2}  ! {udp_sink}"


        logging.info(f"Launch-str:'\r\n{launch_str}\r\n'")
        self.launch_str = launch_str

    def __init__(self, gpref):
        logging.info('My process id is: {}'.format(os.getpid()))

        self.gpref = gpref
        self.should_stop = False

        signal.signal(signal.SIGINT, self.stop_now)
        signal.signal(signal.SIGTERM, self.stop_now)
        logging.info("Set up signal reaction")


        Gst.init()

        self.main_loop = GLib.MainLoop()
        thread = Thread(target=self.main_loop.run)
        thread.start()


        self.build_gstreamer_pipeline()

        self.pipeline = Gst.parse_launch(self.launch_str)
        self.x264enc = self.pipeline.get_by_name("myenc")
        self.queue = self.pipeline.get_by_name("myqueue")
        self.queue.connect("overrun", self.on_overrun)

        self.gs_sink  = self.pipeline.get_by_name("gs_sink")


        self.pipeline.set_state(Gst.State.PLAYING)

        # Set up ZMQ:
        context = zmq.Context()
        self.socket = context.socket(zmq.SUB)
        socket_url = f"tcp://{gpref.zmq_host}:{gpref.zmq_port}"
        logging.info(f"ZMQ Connecting to {socket_url}")
        self.socket.connect(socket_url)
        self.socket.subscribe("")
        self.socket.setsockopt(zmq.RCVTIMEO, 500)

        ## ZMQ Settings changes
        settings_context = zmq.Context()
        self.settings_socket = settings_context.socket(zmq.PULL)
        settings_socket_url = f"tcp://0.0.0.0:{gpref.zmq_settings_port}"
        logging.info(f"ZMQ opening settings server to {settings_socket_url}")
        self.settings_socket.bind(settings_socket_url)


        self.current_bitrate = gpref.initial_bitrate_kbps
        self.x264enc.set_property("bitrate", self.current_bitrate)


        self.bitrate_by_buffer = self.gpref.buffer_feedback
        if not self.bitrate_by_buffer:
            logging.warning("Bitrate by buffer is off")
        self.bitrate_factor = 1.0
        self.const_bitrate = self.gpref.const_bitrate
        if self.const_bitrate:
            logging.warning("Using Const Bitrate")

    def update_buffer_factor(self, queue_time):
        if queue_time == 0:
            self.bitrate_factor = np.min([self.bitrate_factor * 1.05,1.0])
        if 34 < queue_time <= 50 and self.old_queue_time < queue_time:
            self.bitrate_factor = np.max([0.4,self.bitrate_factor * 0.95])
        if 50 < queue_time > 80  and self.old_queue_time < queue_time:
            self.bitrate_factor = np.max([0.05,self.bitrate_factor * 0.85])
        if queue_time > 80  and self.old_queue_time < queue_time:
            self.bitrate_factor = np.max([0.05,self.bitrate_factor * 0.7])
        self.old_queue_time = queue_time

    def loop(self):
        logging.info("Entering loop")
        self.last_reported_queue_time = -1
        last_bitrate = -1
        self.potential_queue_point = None
        old_bitrate_f = 1.0

        try:
            while not self.should_stop:
                queue_time = self.queue.get_property('current-level-time') / 1_000_000
                if self.bitrate_by_buffer:
                    self.update_buffer_factor(queue_time)

                message = None
                try:
                    message = self.socket.recv_json(flags=zmq.NOBLOCK)  # do not block while loop
                except zmq.error.Again:
                    pass
                except JSONDecodeError:
                    continue

                # check message for new bitrate
                bitrate = self.current_bitrate
                if message is not None and "Combined" in message:
                    message = message["Combined"]
                    debug_str = "Got message: "
                    bitrate_key = "bitrate"
                    if not self.multilink:
                        bitrate_key = "modem1"
                        # logging.info("use modem1: {message[bitrate_key]}")
                    if bitrate_key not in message:
                        logging.error("Bitrate not contained in message!")
                    else:
                        try:
                            bitrate = int(message[bitrate_key])
                            if not self.const_bitrate:
                                logging.info(f"{debug_str} bitrate[{bitrate_key}]={bitrate:.0f} kBit/s")
                        except ValueError:
                            logging.error(f"Could not parse bitrate: {message[bitrate_key]}")
                            bitrate = self.current_bitrate
                        if bitrate > gpref.max_bitrate:
                            bitrate = gpref.max_bitrate
                        if bitrate < 2000:
                            logging.warning("Too low bitrate requested!")
                            bitrate = 2000
                        new_bitrate = bitrate

                    if bitrate is None or (self.const_bitrate and (bitrate != self.gpref.initial_bitrate_kbps)):
                        # const bitrate mode --> no change
                        # illegal bitrate value in message -->no change
                        bitrate = self.gpref.initial_bitrate_kbps
                        #logging.info(f"Using initial bitrate/const bitrate: {bitrate}")
                        if bitrate is None:
                            logging.info("Bitrate is None")

                if bitrate != self.current_bitrate or self.bitrate_factor != old_bitrate_f:
                    old_bitrate_f = self.bitrate_factor
                    bitrate_scaled = float(bitrate)
                    if self.bitrate_by_buffer:
                        bitrate_scaled = bitrate_scaled  * self.bitrate_factor
                    self.current_bitrate = bitrate
                    self.x264enc.set_property("bitrate", bitrate_scaled)

        except KeyboardInterrupt:
            logging.info("Got Keyboard Interrupt")
            self.on_exit()

    @debug_log_function
    def on_message(self, bus: Gst.Bus, message: Gst.Message, loop):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            self.pipeline.set_state(Gst.State.NULL)
            self.main_loop.quit()

    @debug_log_function
    def stop_now(self, signum, frame):
        logging.info("Will stop now")
        self.on_exit()

    @debug_log_function
    def on_exit(self):
        logging.info("Exiting Adaptive Streaming")
        self.exit_influx = True
        bus = self.pipeline.get_bus()
        self.pipeline.send_event(Gst.Event.new_eos())

        msg = bus.timed_pop_filtered(1000000000, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg is not None and msg.type == Gst.MessageType.EOS:
            print("Got EOS")
        # time.sleep(1) # give time to end file
        self.should_stop = True
        self.pipeline.set_state(Gst.State.NULL)
        self.main_loop.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)


    logging.info("Starting Adaptive Video Stream")
    gpref = GstreamerSettings.from_yaml_file("gstreamer_pref.yaml")

    avs = AdaptiveStreamer(gpref=gpref)
    avs.loop()
