import logging
import sys
import threading
from threading import Thread
import gi
import signal
import time
import os


gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")

from gi.repository import Gst, GLib, GstApp, GObject


def send_eos_event(ppipeline):
    ppipeline.send_event(Gst.Event.new_eos())
    return False

class StreamReceiver:
    def pad_probe_callback(self, pad, info):
        if  self.should_stop:
            return Gst.PadProbeReturn.OK
        event = info.get_event()
        if event and event.type == Gst.EventType.CUSTOM_DOWNSTREAM:
            structure = event.get_structure()
            if structure and structure.get_name() == "GstRTPPacketLost":
                # Get the number of lost packets from the structure
                seqnum = structure.get_value("seqnum")
                timestamp = structure.get_value("timestamp")
                duration = structure.get_value("duration")
                retry = structure.get_value("retry")
                logging.warning(f"Packet lost: {seqnum}")

        return Gst.PadProbeReturn.OK



    def create_pipeline(self):
        self.pipeline = Gst.Pipeline.new("video-pipeline")
        # Create elements
        udpsrc = Gst.ElementFactory.make("udpsrc", "udpsrc")
        udpsrc.set_property("port", 1234)

        caps = Gst.Caps.from_string("application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96")
        capsfilter = Gst.ElementFactory.make("capsfilter", "capsfilter")
        capsfilter.set_property("caps", caps)

        jitterbuffer = Gst.ElementFactory.make("rtpjitterbuffer", "jitterbuffer")
        jitterbuffer.set_property("latency", 50)
        jitterbuffer.set_property("do-lost", True)

        self.depay = Gst.ElementFactory.make("rtph264depay", "depay")
        parser = Gst.ElementFactory.make("h264parse", "parser")
        timestamper = Gst.ElementFactory.make("h264timestamper","timestamper") #generate missing pts

        framerate_filter = Gst.ElementFactory.make("capsfilter", "framerate-filter")
        framerate_caps = Gst.Caps.from_string("video/x-h264,framerate=30/1")  # Set to 60 FPS
        framerate_filter.set_property("caps", framerate_caps)


        muxer = Gst.ElementFactory.make("mp4mux", "muxer")
        filesink = Gst.ElementFactory.make("filesink", "filesink")
        filesink.set_property("location", "transmitted.mp4")

        # Add elements to the pipeline
        elements = [udpsrc, capsfilter, jitterbuffer, self.depay, parser, timestamper,framerate_filter, muxer, filesink]
        for element in elements:
            self.pipeline.add(element)
        for ind, element in enumerate(elements):
            if ind +1 < len(elements):
                elements[ind].link(elements[ind+1])

    def __init__(self):
        logging.info('My process id is: {}'.format(os.getpid()))

        self.send_out_eos = False
        self.should_stop = False
        signal.signal(signal.SIGINT, self.stop_now)
        signal.signal(signal.SIGTERM, self.stop_now)
        logging.info("Set up signal reaction")

        Gst.init()
        self.main_loop = GLib.MainLoop()
        self.create_pipeline() 

        # Add a pad probe to catch lost packets event on the depayloader's sink pad
        depay_sink_pad = self.depay.get_static_pad("sink")
        if depay_sink_pad:
            depay_sink_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.pad_probe_callback)

        # instruct the bus to emit signals for each received message
        # and connect to the interesting signals
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)

        self.pipeline.set_state(Gst.State.PLAYING)

        logging.info("Starting receiver")
        thread = Thread(target=self.main_loop.run)
        thread.start()

        try:
            while not self.should_stop:
                # Do stuff here or move self.main_loop.run() here instead of additional thread
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Stopping pipeline...")
            self.on_exit()



    def on_message(self, bus: Gst.Bus,message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS and self.send_out_eos:
            logging.info("Got EOS Message, quitting now")
            self.pipeline.set_state(Gst.State.NULL)
            self.main_loop.quit()
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logging.error(f"Pipeline error MSG: err:'{err}',\ndebug:'{debug}'")
            self.main_loop.quit()

        #logging.debug(f"Message='{message}'")
    def stop_now(self,signum, frame):
        logging.info("Will stop now")
        if self.send_out_eos == False:
            logging.info("Going to send out eos event now")
            self.on_exit()
        else:
            logging.error("Already sent out eos event, but still running")
            time.sleep(0.2)
            sys.exit(1)

    def on_exit(self):
        logging.info("Sending EOS")
        GLib.idle_add(send_eos_event, self.pipeline)
        self.send_out_eos = True
        self.should_stop = True

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Starting Adaptive Video Stream Recorder")

    avs = StreamReceiver()
