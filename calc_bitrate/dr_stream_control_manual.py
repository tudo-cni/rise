import time

import zmq
import logging
import json


def main_manual():
    context = zmq.Context()

    logging.info("Connecting to Adaptive Video encode ZMQ Server…")
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://0.0.0.0:5555")
    time.sleep(1)  # wait for bind
    logging.info("Entering loop")
    while True:
        bitrate = input("Enter bitrate (integer):")
        socket.send_json({"bitrate": bitrate})
        logging.info(f"Sent {bitrate} to adaptive coding")

if __name__ == "__main__":
    main_manual()