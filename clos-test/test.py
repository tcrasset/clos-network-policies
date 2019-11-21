#!/usr/bin/env python
"""Tests the controller performance on a Clos-like topology."""

import argparse
import time

from mininet.link import TCLink
from mininet.log import error, info, lg
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.util import waitListening

from clostopo import ClosTopo


def closTest(duration, discovery_time):
    """Test the controller performance on a Clos-like topology.

    Args:
        discovery_time: how long to wait for controller topology discovery in
                        seconds
    """
    # If you modify the topology on next line, you will also likely want to
    # modify the tests done below
    topo = ClosTopo(nCore=2, nEdge=3, nHosts=4, bw=10)
    net = Mininet(topo=topo, switch=OVSKernelSwitch,
                  controller=RemoteController, autoSetMacs=True,
                  autoStaticArp=True, waitConnected=True,
                  link=TCLink)
    net.start()

    info("*** Waiting for controller topology discovery\n")
    for i in range(discovery_time, -1, -1):
        info("\r{:02d}".format(i))
        time.sleep(1)
    info('\n')

    h1, h2, h3, h4 = net.getNodeByName('h1', 'h2', 'h3', 'h4')
    clients = [h1, h2, h3, h4]
    h5, h7, h10, h12 = net.getNodeByName('h5', 'h7', 'h10', 'h12')
    servers = [h5, h10, h7, h12]
    clientServerPairs = zip(clients, servers)

    info("*** Testing basic connectivity\n")
    for (c, s) in clientServerPairs:
        net.ping([c, s])

    info("*** Starting servers\n")
    for s in servers:
        s.sendCmd('iperf -p 5001 -s')

    info("*** Waiting for servers to start\n")

    def abortOnFail(client, server):
        error("\nCannot join server {} from client {}!\nAborting..."
              .format(server, client))
        for s in servers:
            if s.waiting:
                s.sendInt()
                s.waitOutput()
        net.stop()
        exit(1)

    for (c, s) in clientServerPairs:
        if not waitListening(client=c, server=s, port=5001, timeout=5):
            abortOnFail(c, s)
        info('.')
    info('\n')

    info("*** Starting clients\n")
    big = "/home/mininet/clos-test/client.py {} 2 {} 4 3"
    small = "/home/mininet/clos-test/client.py {} 2 {} 1 0"
    h1.sendCmd(big.format("10.0.0.5", duration))
    h2.sendCmd(big.format("10.0.0.10", duration))
    h3.sendCmd(small.format("10.0.0.7", duration))
    h4.sendCmd(small.format("10.0.0.12", duration))

    info("*** Measuring\n")
    for i in range(duration + 5, -1, -1):
        info("\r{:03d}".format(i))
        time.sleep(1)
    info('\n')

    info("*** Waiting for clients to finish\n")
    results = {}
    for c in clients:
        results[c] = c.waitOutput()
        info('.')
    info('\n')

    info("*** Stopping servers\n")
    for s in servers:
        s.sendInt()
        s.waitOutput()

    info("*** Measured bandwidths\n")
    for (c, out) in results.items():
        info("{}: {}".format(c, out))

    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", help="test duration in seconds",
                        type=int, default=60)
    parser.add_argument("--discovery", help="discovery time in seconds",
                        type=int, default=3)
    args = parser.parse_args()

    if (args.duration < 30):
        error("Test duration should be at least 30s")
        exit(1)

    lg.setLogLevel('info')
    closTest(args.duration, args.discovery)
