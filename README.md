# RISE - Reliable Intelligent Stream Encoding - Code

This code is published in conjunction with the research paper titled "*RISE: Multi-Link Proactive Low-Latency Video Streaming for Teleoperation in Fading Channels*" published in the Vehicular Technology Conference Spring 2025 (see section [Bibtex and Citation](#Bibtex)). 
RISE enables  channel-adaptive real-time video encoding in single- or multi-link configurations.

## Table of Contents
- [RISE Demonstration Video](#RISE Demonstration Video)
- [Architecture Overview](#Architecture-Overview)
- [Installation and Setup](#Installation-and-Setup)
- [Running the System](#Running-the-System)
- [Kernel Patch](#Applying a Kernel Patch)
- [SEAMLESS Setup](#Setup-SEAMLESS-Multi-Link)
- [Make Videos Loopable](#make-videos-loopable)
- [Bibtex](#Bibtex)

## RISE Demonstration Video

This video is additional material to the paper:

https://github.com/user-attachments/assets/77f8478c-494a-4922-bdcf-6cac1326431a

## Architecture Overview

The RISE system comprises multiple components split across the **User Equipment (UE)** and **Receiver**:

| Component                  | Runs On       | Description |
|---------------------------|---------------|-------------|
| Modem Monitor             | UE            | Queries 5G modem state |
| Bitrate Estimator         | UE            | Calculates available bitrate |
| SEAMLESS (optional)       | UE + Receiver | Enables multi-link video streaming |
| Adaptive Video Encoder    | UE            | Dynamically encodes video based on channel feedback |
| Video Player / Recorder   | Receiver      | Receives and displays or stores the stream |


## Installation and Setup
### Prerequisites 
- Debian system
- [Docker](https://docs.docker.com/engine/install/) 
- Access to compatible 5G modems (e.g., Quectel RM520)
- Optional: [SEAMLESS](https://github.com/tudo-cni/seamless) installed on both UE and receiver

While this code is written to be run inside docker, there may be restrictions based on the host OS due to the hardware access. 
The code has been tested on Ubuntu 22.04 and 24.04 systems. 

### Configuration 

**Monitor:**
- AT-Ports: The path to the at-ports of the Quectel RM520 modems, which are used to query the current 5G connectivity.
- ZQM-Port: The port on which a ZMQ-Publisher is created, to publish the queried data from the modems
- Modem names: The names of the modems, which are used in the ZMQ publisher to distinguish between both modems. 
This parameter has to be matched with the data rate calculation and the encoder part. 
Thus, it needs to be a common name like "modem" with an increasing number after it.

**Data Rate Calculation**
- Applicatin Overhead: Portion of the overhead in the overall transmission (IP, UDP, SEAMLESS, ...)
- Socket in port: Port of the monitor part ZQM Publisher#
- Socket out port: Port of the ZMQ Publisher transmitting the calculated data rate to the adaptive encoder
- Send combined func: Function used to calculate the data rate, which is possible via all available links.
- Cell Params: A list of cell parameters, as follows

For each 5G cell: 
- Measurement Modem Tag: The name of modem, which shall be used as a prefix before the number. This has to be matched with the monitor part.
- Cell Bandwidth: The Bandwidth of the cells in MHz
- Number of Layers: The number of MIMO layers used
- Mu Subcarrier Spacing: The Subcarrier spacing index (overwritten, when queried from the modem)
- Scaling Factor: The scaling factor used to scale the 5G throughput
- Downlink Percentage: The portion of the resources, which can be used for downlink transmissions
- Own Utilization Factor: The portion of the resources, which can be used
- Maximum Tx power: The maximum transmit power the modem emits
- Max MCS: The maximum modulation and coding scheme index that can be used 

**Adaptive Video Encoder**
- Source element: The gstreamer video source element to choose. E.g. a camera source or a test source
- Use file source: If a file source shall be used instead of the source element
- File: If file source is enabled, this file shall be played
- Loop file: Whether the file shall be looped indefinitely. For this, the file is not allowed to have a defined length (see section [Make file Loopable](#Make Videos Loopable)). 
- Encoder settings: Settings, which shall be passed to the gstreamer h264 video encoder 
- Initial bitrate kbps: The initial bitrate to use for video streaming in kbit/s
- Max bitrate: The maximum bitrate to use. If a higher bitrate is received, the video bitrate is capped to this bitrate.
- Buffer feedback: Wheter buffer feedback shall be used. If this is disabled, packet losses happen. If this is enabled, packet losses are avoided by decreasing the video bitrate.
- Const bitrate: If this is enabled, constant bitrate encoding with the initial bitrate is used. Still, buffer feedback may impact the video bitrate.
- Stream target: The address, where the video stream shall be sent to
- Stream port: The port, the video stream is sent to
- ZMQ host: The address of the ZMQ publisher of the data rate calculator
- ZMQ port: The port of the ZMQ publisher

### Applying a Kernel Patch
To prevent packet drops on "tun" interfaces, a kernel patch has been developed. 
It has been published in conjunction with the paper *The NODROP Patch: Hardening Secure Networking for Real-time Teleoperation by Preventing Packet Drops in the Linux TUN Driver* in this [repository](https://github.com/tudo-cni/nodrop). 

```bibtex
@InProceedings{gebauer2025,
	Author = {Gebauer, Tim and Schippers, Simon and Wietfeld, Christian},
	Title = {{The NODROP Patch: Hardening Secure Networking for Real-time Teleoperation by Preventing Packet Drops in the Linux TUN Driver}},
	Booktitle = {IEEE 102th Vehicular Technology Conference (VTC-Fall)},
	Address = {Chengdu, China},
	Month = {oct},
	Year = {2025},
	Keywords = {Linux; Secure Networking; Video Streaming; Virtual Private Networks},
} 
```



### Setup SEAMLESS Multi-Link
To setup [SEAMLESS](https://github.com/tudo-cni/seamless), follow the building instructions on the github page of SEAMLESS.  
SEAMLESS needs to be run on **both** sides (Sender, Receiver) in order to split and reassemble the data streams.
Thus, this installation guide needs to be followed on the receiver and on the sender. 
The ip configuration (local_ip, remote_ip) need to be adapted for both.  
Example configuration files for the UE and the server are provided.

> [!WARNING]
> SEAMLESS does not reconnect to ZMQ Publishers! So always restart SEAMLESS, if ZMQ is restarted. 
> Start SEAMLESS after the ZMQ Publisher!

Copy the built SEAMLESS executable to the user binary directoy and name it seamless
```bash
sudo cp target/release/seamless-cli /usr/bin/seamless
```

Place service file under /lib/systemd/system/seamless@.service
@ is a placeholder for the config .yaml file. 
```text
[Unit]
Description=SEAMLESS Multilink with %I configuration
Wants=network.target

[Service]
User=root
ExecStart=/usr/bin/seamless -c /etc/seamless/%i.yaml
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Create a SEAMLESS configuration file  under '/etc/seamless/.....yaml'.
The configuration file is case-sensitive.
You can copy the adaptivechannel.yaml config file and adapt from there: 
```bash
sudo mkdir -p /etc/seamless/
sudo cp adaptivechannel.yaml /etc/seamless/
```
Then start the associated service. If the configuration file is named adaptivechannel.yaml, this is the command to start the service:
```
sudo systemctl start seamless@adaptivechannel.service 
```

To get and **f**ollow the output of seamless service
```bash
sudo journalctl -u seamless@adaptivechannel.service -f 
```


## Running the System
Before running, please check the parametrization of the whole setup. 
The default configuration of the code will assume two modems connected and all parts are run on one system. 
Thus, SEAMLESS multi-link is not enabled by default. If multi-link shall be used, at least the IP-configuration needs to be customized. 

1. Run the modem monitor
```bash
docker compose up monitor
```
2. Run the bitrate calculation
```bash
docker compose up cal_bitrate
```
3. Run Seamless
See the instructions on [setting up Seamless](#Setup SEAMLESS Multi-Link) first. If this is done, it can be started like this: 
```bash
sudo systemctl start seamless@adaptivechannel.service
```
4. Run the videostream encoder
```bash
docker compose up videostream
```
5. Run the videostream player or recorder
```bash
xhost -local:docker
docker compose up player
```




## Make Videos Loopable


Stream a file locally and write the received stream to a file, so no end of the stream and no length of the file is present.

Start this gstreamer command first in one terminal:
```bash
gst-launch-1.0 udpsrc port=10600 ! application/x-rtp-stream ! rtpstreamdepay name=pay1 ! rtph264depay ! h264parse ! video/x-h264,alignment=nal ! filesink location=my_timeless_video.mp4
```
Then, start this in another terminal:

```bash
gst-launch-1.0 filesrc location=my_video.mp4 ! queue ! decodebin ! videoconvert ! x264enc ! h264parse config-interval=-1 ! rtph264pay pt=96 ! rtpstreampay name=pay0 ! udpsink host=127.0.0.1 port=10600
```
The received file my_timeless_video.mp4 can now be looped.


## Bibtex
This work has been published in the IEEE Vehicular Technology Conference Spring 2025 (VTC2025-Spring) in Oslo, Norway.
If you find this work useful for your research, please consider citing it:
```bibtex
@InProceedings{Schippers2025a,
	Author = {Schippers, Hendrik and Gebauer, Tim and Heimann, Karsten and Wietfeld, Christian},
	Title = {{RISE}: {M}ulti-Link Proactive Low-Latency Video Streaming for Teleoperaton in Fading Channels},
	Booktitle = {2025 IEEE 101st Vehicular Technology Conference (VTC2025-Spring)},
	Address = {Oslo, Norway},
	Month = {jun},
	Year = {2025}
} 

```
## Questions
For issues and questions, please feel free to contact one of the authors.