FROM ubuntu:24.04
WORKDIR /home

RUN apt-get update && apt-get upgrade -y -qqq && \
apt-get install build-essential curl nano -y -q

# Install GStreamer
RUN apt-get install \
libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x \
gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 \
gstreamer1.0-pulseaudio gstreamer1.0-plugins-rtp gstreamer1.0-rtsp \
vainfo gstreamer1.0-vaapi intel-media-va-driver libva-dev -y -q

ENV LIBVA_DRIVER_NAME=iHD

# Install python packages
RUN apt-get install python3 \
python3-pip \
python3-numpy \
python3-gi \
python3-gst-1.0 \
libzmq3-dev \
python3-pip \
python3-wheel \
python3-pip \
python3-setuptools \
python3-zmq \
python3-yaml \
python3-influxdb-client -y -q 


RUN pip3 install dataclass-wizard --break-system-packages && \
rm -rf /var/lib/apt/lists/*



ENV DISPLAY=host.docker.internal:0.0
