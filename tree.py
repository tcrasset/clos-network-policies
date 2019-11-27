# Copyright 2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#
# Modified by Tom Crasset and Thibault Renaud for the course of
# Network Infrastructures at 2019/2020 at University of Liege
# to implement a Spanning Tree Controller Policy.

from pox.core import core
import pox.openflow.libopenflow_01 as of


log = core.getLogger()


class Tree_Controller(object):
    """
    A Tree_Controller object is created for each switch that connects.

    A Connection object for that switch is passed to the __init__ function.
    Is supposed to be used with a Clos Topology.

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
    """

    def __init__(self, connection, nCore, nEdge, nHosts):
        """
        Initializes the Tree_Controller object.

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

        # We want to keep core switch s1
        if(self.switch_id in self.edgeSwitchIDs):
            self._activate_core(1)

        # This binds our PacketIn event listener
        connection.addListeners(self)

        self.mac_to_port = {}

    def _activate_core(self, coreSwitchPort):
        """
        Instructs the edge switch to block every port to a core switch except
        the port `coreSwitchPort`.

        Port number between edge and core switches are in [1, nCore]
        Every core switch is connected to the same port on every edge switch
        E.g. core switch s1 will connect to port 1 on s3, s4 and s5.

        Parameters
        ----------
        coreSwitchPort : int
            Port to the coreSwitch

        Returns
        -------
        None
        """

        ports_to_block = [p for p in range(1, self.nCore+1)
                          if p != coreSwitchPort]
        for port in ports_to_block:
            log.debug(" S{} deactivating port {}".format(self.switch_id, port))
            msg = of.ofp_port_mod()
            msg.port_no = self.connection.ports[port].port_no
            msg.hw_addr = self.connection.ports[port].hw_addr
            msg.mask = of.OFPPC_NO_FLOOD
            msg.config = of.OFPPC_NO_FLOOD
            self.connection.send(msg)

        return

    def resend_packet(self, packet_in, out_port):
        """
        Instructs the switch to resend a packet that it had sent to us.

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
        """
        Implement switch like behavior.

        Sends a packet out to a port depending on specific conditions and
        installs rules in the flow table of the corresponding switch
        via OpenFlow messages.

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

        source = str(packet.src)
        dest = str(packet.dst)

        # Learn the port for the source MAC
        self.mac_to_port[source] = packet_in.in_port

        if dest in self.mac_to_port:
            out_port = self.mac_to_port[dest]

            # Set fields to match received packet
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet_in)
            msg.idle_timeout = 100
            msg.hard_timeout = 1000

            # Send packet out the associated port
            msg.actions.append(of.ofp_action_output(port=out_port))
            self.connection.send(msg)
            self.resend_packet(packet_in, out_port)
            log.debug("  S{} - Installing flow: {} Port {} -> {} Port {}".format(
                self.switch_id, source, packet_in.in_port, dest, out_port))

        else:
            # Flood the packet out to every port but the input port
            self.resend_packet(packet_in, of.OFPP_FLOOD)
            log.debug("  S{} - Flooding packet from {} {} to {}".format(
                self.switch_id, source, packet_in.in_port, dest))

        return

    def _handle_PacketIn(self, event):
        """
        Handles packet in messages from the switch.

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

        return


def launch(nCore, nEdge, nHosts):
    """
    Starts the component when calling from the command line.

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

    def start_switch(event):
        log.debug("Controlling %s" % (event.connection,))
        Tree_Controller(event.connection, int(nCore), int(nEdge), int(nHosts))

    core.openflow.addListenerByName("ConnectionUp", start_switch)
