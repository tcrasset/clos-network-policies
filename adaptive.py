# Copyright 2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#
# Modified for the course of Network Infrastructures at 2019/2020 at
# University of Liege to implement a Adaptive Routing Controller Policy


from pox.core import core
from pox.lib.recoco import Timer
import pox.openflow.libopenflow_01 as of
from pox.openflow.of_json import flow_stats_to_list


log = core.getLogger()


class Adaptive_Controller(object):
    """Controller handling the network with an adaptive routing policy. 

    A Adaptive_Controller object is created for each switch that connects.
    A Connection object for that switch is passed to the __init__ function.
    Is supposed to be used with a Clos Topology.

    In this controller, the switch will send a flow to the link which is the
    least loaded.

    Arguments
    ----------
    switch_id : int
        ID used to uniquely identify the switch in a topology
    coreSwitchIDs : list of int
        IDs of core switches in the topology
    edgeSwitchIDs : list of int
        IDs of edge switches in the topology
    mac_to_port : dict of str: int
        Dictionnary mapping MAC addresses of type pox.lib.addresses.EthAddr to ports
    time_interval : int
        Time interval between two PortStatsRequests
    current_port_throughput : dict of int: float
        Dictionnary storing the throughput of links connected to switch ports
    
    Notes
    ----------
    A pox.lib.recoco.Timer thread is launched at initialization.
    This timer will call `_sendPortStatsRequests` every `time_interval` seconds.
    """

    def __init__(self, connection, nCore, nEdge, nHosts):
        """Initializes the Adaptive_Controller object.

        Parameters
        ----------
        connection : pox.lib.revent.connection
            Connection from the controller to the switch 
        nCore : int
            Number of core switches in the Clos Topology
        nEdge : int
            Number of edge switches in the Clos Topology 
        nHosts : int
            Number of hosts per edge switch in the Clos Topology 
        """
        self.connection = connection
        self.nCore = nCore
        self.nEdge = nEdge
        self.nHosts = nHosts

        self.switch_id = connection.dpid
        self.coreSwitchIDs = list(range(1, self.nCore+1))
        self.edgeSwitchIDs = list(
            range(self.nCore + 1, self.nCore + 1 + self.nEdge))

        # This binds our PacketIn event listener
        connection.addListeners(self)

        self.time_interval = 1
        self.current_port_throughput = {}
        core.openflow.addListenerByName(
            "PortStatsReceived", self._handle_portstats_received)
        Timer(timeToWake=self.time_interval,
              callback=self._sendPortStatsRequests, recurring=True)

        self.mac_to_port = {}

    def is_core(self):
        """Determines whether the switch is a core switch.

        The switch IDs in a Clos Network are deterministic, i.e. a core
        switch will have IDs ranging from [1, nCore + 1]
        Parameters
        ----------
        None

        Returns
        -------
        True if the switch is a core switch.
        False otherwise.
        """
        if self.switch_id in self.coreSwitchIDs:
            return True
        return False

    def sent_from_core(self, port):
        """Determines whether or not the packet was sent from a core switch.

        The ports in a Clos Network are deterministic, i.e. an edge
        switch will receive a packet on port `port` from core switch
        with ID `port`.

        Parameters
        ----------
        port : int
            The receiving port of a given switch

        Returns
        -------
        True if the port is associated with a core switch.
        False otherwise.
        """
        return port in self.coreSwitchIDs

    def get_throughput_at_port(self, port):
        """Gives the current throughput of a link going out of `port`.

        Parameters
        ----------
        port : int
            The outgoing port of a switch

        Returns
        -------
        float
            Link throughput in Kbps
        """

        return self.current_port_throughput[(self.switch_id, port)]

    def resend_packet(self, packet_in, out_port):
        """Instructs the switch to resend a packet that it had sent to us.

        Parameters
        ----------
        packet_in : ofp_packet_in object
            Packet which the switch had sent to the controller due to a table-miss
        out_port : int
            Port to send the packet out of

        Returns
        -------
        None
        """
        msg = of.ofp_packet_out()
        msg.data = packet_in

        # Add an action to send to the specified port
        action = of.ofp_action_output(port=out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)

        return

    def act_like_switch(self, packet, packet_in):
        """Implement switch like behavior.

        Sends a packet out to a port depending on specific conditions and
        installs rules in the flow table of the corresponding switch
        via OpenFlow messages.

        When it comes to transferring unknown packets,
        there are multiple cases depending on the nature of the switch:

        1. The switch is a core switch:

            - IF the destination is already in the dictionnary, add port
              to dictionnary and entry to flow table and forward the packet
              out to the port specified by the flow table

            OR

            - IF the destination is not present in the dictionnary, flood
             the packet out to the edge switch ports

        2. Switch is an edge switch and gets a packet from a core:

            - IF the destination is already in the dictionnary forward the packet
            out to the port specified by the flow table.

            - IF the destination is not present in the dictionnary,
            flood the packet towards the hosts.

        3. Switch is an edge switch and gets a packet from a host:
            - Add host address to port mapping to the dictionnary and
            select optimal output port using adaptive routing, install
            that flow in the switch flow table and forward the packet out
            that port.

        Parameters
        ----------
        packet : pox.lib.packet
            Packet that the switch sent up to the controller
        packet_in : ofp_packet_in object
            OpenFlow message

        Returns
        -------
        None
        """
        # Learn the port for the source MAC
        source = str(packet.src)
        dest = str(packet.dst)

        if self.is_core():
            self.mac_to_port[source] = packet_in.in_port
            # Add port to dictionnary and entry to flow table if it is present
            if dest in self.mac_to_port:
                out_port = self._install_flow(source, dest, packet_in)
                self.resend_packet(packet_in, out_port)
            else:
                # Flood the packet out to the edge switch ports
                self.resend_packet(packet_in, of.OFPP_FLOOD)
                log.debug("  S{} - Flooding packet from {} {} to edge switch ports".format(
                    self.switch_id, source, packet_in.in_port))

        # Switch is an edge switch and gets a packet from a core switch
        elif self.sent_from_core(packet_in.in_port):
            # Add port to dictionnary and entry to flow table if it is present
            if dest in self.mac_to_port:
                out_port = self._install_flow(source, dest, packet_in)
                self.resend_packet(packet_in, out_port)

            else:
                # Flood the packet out to the hosts only
                ports = [port for port in range(
                    1, self.nCore + self.nHosts + 1) if port not in self.coreSwitchIDs]
                for p in ports:
                    self.resend_packet(packet_in, out_port=p)
                log.debug("  S{} - Flooding packet from {} {} to host ports :{}".format(
                    self.switch_id, source, packet_in.in_port, ports))

        # Switch is an edge switch and gets a packet from a host
        else:

            # Add host address to port mapping to the dictionnary
            self.mac_to_port[source] = packet_in.in_port

            # Select optimal output port (adaptive routing)
            min_throughput = float("inf")
            for port in self.coreSwitchIDs:
                throughput = self.get_throughput_at_port(port)
                if(throughput < min_throughput):
                    min_throughput = throughput
                    out_port_to_core = port
            self._install_flow(source, dest, packet_in,
                               specific_out_port=out_port_to_core)
            self.resend_packet(packet_in, out_port=out_port_to_core)
            log.debug("  S{} - Forwarding packet from {} {} out to port {}".format(
                self.switch_id, source, packet_in.in_port, out_port_to_core))
        return

    def _handle_PacketIn(self, event):
        """Handles packet in messages from the switch.

        Parameters
        ----------
        event : pox.lib.revent
            Event that the controller handles from the connected switch

        Returns
        -------
        None
        """
        packet = event.parsed
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp
        self.act_like_switch(packet, packet_in)

    def _install_flow(self, source,  destination, packet_in, specific_out_port=None):
        """Installs a flow in a switch table.

        A flow is discriminated with regards to protocol and source/destination ports.

        Returns:
        out_port
        """

        # Add to dictionnary
        # Send packet out the associated port
        if specific_out_port == None:
            out_port = self.mac_to_port[destination]
        else:
            out_port = specific_out_port

        log.debug(" S{} - Installing flow: {} Port {} -> {} Port {}".format(self.switch_id, source,
                                                                            packet_in.in_port, destination, out_port))

        # Set fields to match received packet, removing information we don't want to keep
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet_in)
        msg.match.in_port = None
        msg.match.dl_vlan = None
        msg.match.dl_vlan_pcp = None
        msg.match.nw_tos = None
        msg.idle_timeout = 100
        msg.hard_timeout = 1000
        msg.actions.append(of.ofp_action_output(port=out_port))
        self.connection.send(msg)

        return out_port

    def _sendPortStatsRequests(self):
        """Sending a PortStatsRequest to the switch.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.connection.send(of.ofp_stats_request(
            body=of.ofp_port_stats_request()))
        log.debug(" S{} - Sent one port stats request".format(self.switch_id))
        return

    def _handle_portstats_received(self, event):
        """Handles a PortStatsRequest at the switch and computes throughput.

        Fills or updates the dictionnary `self.current_port_throughput` with throughputs
        of each link of the switch in Kbps.
        The throughput is calculated every `self.time_interval` seconds.

        BUG: The switch receives the PortStatsReceived object of all the switches 
        controlled by this controller.

        Parameters
        ----------
        event: PortStatsReceived
            Event listening to PortStatsReceived from openflow

        Returns
        -------
        None
        """

        log.debug(
            " S{} - PortStatsReceived from switch S{}".format(self.switch_id, event.connection.dpid))
        for stat in flow_stats_to_list(event.stats):
            current_bytes = stat['tx_bytes']
            key = (event.dpid, stat['port_no'])
            if key in self.current_port_throughput:
                throughput = (
                    current_bytes - self.current_port_throughput[key])/self.time_interval/10**3
                self.current_port_throughput[key] = throughput
            else:  # Initilisation
                self.current_port_throughput[key] = current_bytes
        return


def launch(nCore, nEdge, nHosts):
    """Starts the component when calling from the command line.

    Parameters
    ----------
    nCore : int
        Number of core switches in the Clos Topology
    nEdge : int
        Number of edge switches in the Clos Topology
    nHosts : int
        Number of hosts per edge switch in the Clos Topology

    Returns
    -------
    None    
    """

    log.debug("Controller started with the following arguments:")
    log.debug("nCore={}, nEdge={}, nHosts ={}".format(nCore, nEdge, nHosts))

    controller = None

    def start_switch(event):
        log.debug("Controlling %s" % (event.connection,))
        controller = Adaptive_Controller(
            event.connection, int(nCore), int(nEdge), int(nHosts))

    core.openflow.addListenerByName("ConnectionUp", start_switch)
