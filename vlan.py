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
# University of Liege to implement a VLAN Controller Policy


from pox.core import core
import pox.openflow.libopenflow_01 as of

from tenants import Tenants


log = core.getLogger()


class VLAN_Controller(object):
    """Controller handling the network like a VLAN

    A VLAN_Controller object is created for each switch that connects.
    A Connection object for that switch is passed to the __init__ function.
    Is supposed to be used with a Clos Topology.

    In this controller, the switch is designed to behave like in a VLAN.
    That is, each host will be associated to a given VLAN id, i.e. a core switch,
    and packets will be routed to the corresponding core switch of the destination.

    Example: 
    If h1 has vlan_id = 1 and h2 has vlan_id = 2, a packet which destination
    is h1 will be sent through core switch with switch_id = 1 and a packet which 
    destination is h2 will be sent through core switch with switch_id = 2.

    Arguments
    ----------
    switch_id : int
        ID used to uniquely identify the switch in a topology
    coreSwitchIDs : list of int
        IDs of core switches in the topology
    edgeSwitchIDs : list of int
        IDs of edge switches in the topology
    tenants: Tenants object
        Object associating host to a tenant i.e. a core switch
    vlan_id: int
        ID determining to which VLAN a host belongs to. There are
        `nCore` VLANs and `vlan_id` is initialized to 1.
    mac_to_port : dict of str: int
        Dictionnary mapping MAC addresses of type pox.lib.addresses.EthAddr to ports
    """

    def __init__(self, connection, nCore, nEdge, nHosts):
        """Initializes the VLAN_Controller object.

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

        self.tenants = Tenants(n_vlans=nCore)
        self.vlan_id = 1

        # This binds our PacketIn event listener
        connection.addListeners(self)

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

    def _install_flow(self, source,  destination, packet_in):
        """Installs a flow in a switch table.

        Parameters
        ----------
        packet : pox.lib.packet
            Packet that the switch sent up to the controller
        packet_in : ofp_packet_in object
            OpenFlow message

        Returns
        -------
        out_port
        """

        # Add to dictionnary
        # Send packet out the associated port
        out_port = self.mac_to_port[destination]

        log.debug("  S{} - Installing flow: {} Port {} -> {} Port {}".format(
            self.switch_id, source, packet_in.in_port, destination, out_port))

        # Set fields to match received packet
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet_in)
        msg.idle_timeout = 100
        msg.hard_timeout = 1000
        msg.actions.append(of.ofp_action_output(port=out_port))
        self.connection.send(msg)

        return out_port

    def act_like_switch(self, packet, packet_in):
        """Implement switch like behavior.

        Sends a packet out to a port depending on specific conditions and
        installs rules in the flow table of the corresponding switch
        via OpenFlow messages.
        Once a new packet is received, the controller adds a rule to the flow
        table of the corresponding switch.

        When it comes to transferring unknown packets,
        there are multiple cases depending on the nature of the switch:
        1. The switch is a core switch:
            - Flood the packet out to the edge switch ports
        2. Switch is an edge switch and gets a packet from a core:
            - Flood the packet toward host ports
        3. Switch is an edge switch and gets a packet from a host:
            - If host has no tenant yet, assign him a tenant
            - Then, forward the packet towards the tenant (core switch)

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
        log.debug(" S{} - {}".format(self.switch_id, packet))

        self.mac_to_port[source] = packet_in.in_port

        if dest in self.mac_to_port:
            out_port = self._install_flow(source, dest, packet_in)
            self.resend_packet(packet_in, out_port)

        else:
            if self.is_core():
                # Flood the packet out to the edge switch ports
                self.resend_packet(packet_in, of.OFPP_FLOOD)
                log.debug("  S{} - Flooding packet from {} {} to edge switch ports".format(
                    self.switch_id, source, packet_in.in_port))

            # Switch is an edge switch and gets a packet from a core
            elif self.sent_from_core(packet_in.in_port):
                ports = [port for port in range(
                    1, self.nCore + self.nHosts + 1) if port not in self.coreSwitchIDs]
                for p in ports:
                    self.resend_packet(packet_in, out_port=p)
                log.debug("  S{} - Flooding packet from {} {} to host ports :{}".format(
                    self.switch_id, source, packet_in.in_port, ports))

            # Switch is an edge switch and gets a packet from a host
            else:
                out_port_to_tenant = self.tenants.getVLAN(packet.src)
                # If host has no tenant yet, assign him a tenant
                if out_port_to_tenant == -1:
                    self.tenants.addToVLAN(packet.src, out_port=self.vlan_id)
                    out_port_to_tenant = self.vlan_id
                    self.vlan_id = (self.vlan_id) % self.tenants.n_vlans + 1

                self.resend_packet(packet_in, out_port=out_port_to_tenant)
                log.debug("  S{} - Forwarding packet from {} {} out to port {}".format(
                    self.switch_id, source, packet_in.in_port, out_port_to_tenant))

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

    def start_switch(event):
        log.debug("Controlling %s" % (event.connection,))
        VLAN_Controller(event.connection, int(nCore), int(nEdge), int(nHosts))

    core.openflow.addListenerByName("ConnectionUp", start_switch)
