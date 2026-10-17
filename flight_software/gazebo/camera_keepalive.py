#!/usr/bin/env python3
"""
camera_keepalive.py -- keep the recording cameras rendering (headless runs).

    /usr/bin/python3 camera_keepalive.py      # system python: gz.transport13

gz-sensors skips rendering a camera whose image topic has no subscriber, and
the sensor's own <save> does not count as one -- so without this, recorded
runs saved no frames. It subscribes to the three image topics and discards
the messages; the sensors' <save> writes the PNGs.
"""
import time

from gz.msgs10.image_pb2 import Image
from gz.transport13 import Node

W = "/world/coconut_plantation"
TOPICS = [
    f"{W}/model/coconut_quadplane/link/chase_link/sensor/chase/image",
    f"{W}/model/overview_cam/link/link/sensor/overview/image",
    f"{W}/model/coconut_quadplane/link/nosecam_link/sensor/esp32cam/image",
]


def main():
    node = Node()
    for t in TOPICS:
        node.subscribe(Image, t, lambda msg: None)
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    main()
