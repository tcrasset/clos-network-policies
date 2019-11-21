#!/usr/bin/env python
"""Script to generate iperf streams up to a given bandwidth."""

from __future__ import print_function

import socket
import subprocess
import sys
import threading
import time


usage = """
Usage: {0} DST_IP BANDWIDTH DURATION N_FLOWS DELAY

Args:
    DST_IP: IP address of destination server (e.g. 10.0.0.5)
    BANDWIDTH: Bandwidth of each individual flow in Mbps
    DURATION: Overall duration of the measure
    N_FLOWS: Number of flows to generate
    DELAY: Number of seconds to wait between the start of each flow

Example:
    {0} 10.0.0.5 2 60 3 5 would start:
    - a 60s 2-Mbps flow after 0s;
    - a 55s 2-Mbps flow after 5s;
    - a 50s 2-Mbps flow after 10s.
""".format(sys.argv[0])


def wrong_arg(msg):
    """Print the given wrong argument message and usage, then exits."""
    print(msg, file=sys.stderr)
    print(usage, file=sys.stderr)
    exit(1)


class IperfThread(threading.Thread):
    """Thread that executes an iperf after the specified delay.

    Args:
        dst: destination IP
        bw: iperf bandwidth in Mbps
        duration: duration of measure in seconds
        delay: delay after which iperf is launched

    After thread execution, the measured bandwidth is in result.
    """

    def __init__(self, dst, bw, duration, delay):
        super(IperfThread, self).__init__()
        self._dst = dst
        self._bw = bw
        self._duration = duration
        self._delay = delay

    def run(self):
        time.sleep(self._delay)
        cmd = ["iperf", "-f", "m", "-b", "{}M".format(self._bw)]
        cmd += ["-t", str(self._duration), "-c", self._dst]
        result = subprocess.check_output(cmd)
        index = 6 if self._duration >= 10 else 7
        self.result = float(result.split('\n')[-2].split()[index])


def measure(dst, bw, duration, n_flows, delay):
    """Do the iperf measures and return the sum of stream bandwidths."""
    threads = []
    for i in range(0, n_flows):
        t = IperfThread(dst, bw, duration - i * delay, i * delay)
        threads.append(t)
    for t in threads:
        t.start()

    sum = 0.0
    for t in threads:
        t.join()
        sum += t.result
    return sum


if __name__ == "__main__":
    if len(sys.argv) != 6:
        wrong_arg("Wrong number of arguments!")
    _, dst, bw, duration, n_flows, delay = sys.argv

    try:
        socket.inet_aton(dst)
    except socket.error:
        wrong_arg("{} is not a valid IP address!".format(dst))

    try:
        bw = float(bw)
    except ValueError:
        wrong_arg("{} is not a valid bandwidth in Mbps!".format(bw))

    def _parse_int(s, what):
        try:
            return int(s)
        except ValueError:
            wrong_arg("{} is not a valid {}!".format(s, what))

    duration = _parse_int(duration, "duration in seconds")
    n_flows = _parse_int(n_flows, "number of flows")
    delay = _parse_int(delay, "delay in seconds")

    result = measure(dst, bw, duration, n_flows, delay)
    print(result, "Mbps")
