FROM ubuntu:24.04
WORKDIR /home

RUN apt-get update && apt-get upgrade -y -qq && \
apt-get install build-essential curl -y -q


# Install GStreamer
RUN apt-get install \
libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x \
gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 \
gstreamer1.0-pulseaudio gstreamer1.0-plugins-rtp gstreamer1.0-rtsp -y -q && \
rm -rf /var/lib/apt/lists/*

#ENV DISPLAY=host.docker.internal:0.0
ENV DISPLAY=:0.0
COPY gstreamer_player.py /home
