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
    """
    A VLAN_Policy object is created for each switch that connects.
    A Connection object for that switch is passed to the __init__ function.
    """
    def __init__ (self, connection, nCore, nEdge, nHosts):
        # Keep track of the connection to the switch so that we can
        # send it messages!
        self.connection = connection
        self.switch_id = connection.dpid
        self.nCore = nCore
        self.nEdge = nEdge
        self.nHosts = nHosts

        self.coreSwitchIDs = []
        self.edgeSwitchIDs = []
        self.edgeToCoreLink = []
        self.HostToEdgeLink = []

        self.recreate_topology()

        self.tenants = Tenants(n_vlans=nCore)
        self.vlan_id = 1

        # This binds our PacketIn event listener
        connection.addListeners(self)

        # Use this table to keep track of which ethernet address is on
        # which switch port (keys are MACs, values are ports).
        self.mac_to_port = {}
    

    def recreate_topology(self):
        self.coreSwitchIDs = list(range(1,self.nCore+1))
        self.edgeSwitchIDs = list(range(self.nCore + 1, self.nCore + 1 + self.nEdge))
        self.edgeToCoreLink = [(e, c) for e in self.edgeSwitchIDs for c in self.coreSwitchIDs]
        
        hostNo=1
        self.HostToEdgeLink = []
        for e in self.edgeSwitchIDs:
            for h in range(hostNo, hostNo + self.nHosts):
                self.HostToEdgeLink.append((h,e))
            hostNo += self.nHosts


    def is_core(self):
        if self.switch_id in self.coreSwitchIDs:
            return True
        return False

    def is_edge(self):
        if self.switch_id in self.edgeSwitchIDs:
            return True
        return False



    def sent_from_core(self, port):
        return port in self.coreSwitchIDs


    def resend_packet (self, packet_in, out_port):
        """
        Instructs the switch to resend a packet that it had sent to us.
        "packet_in" is the ofp_packet_in object the switch had sent to the
        controller due to a table-miss.
        """
        msg = of.ofp_packet_out()
        msg.data = packet_in

        # Add an action to send to the specified port
        action = of.ofp_action_output(port = out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)


    def act_like_switch(self, packet, packet_in):
        """
        Implement switch-like behavior.
        """

        # Learn the port for the source MAC
        source = str(packet.src)
        dest = str(packet.dst)
        print(packet)

        self.mac_to_port[source] = packet_in.in_port

        if dest in self.mac_to_port:
            # Add to dictionnary
            # Send packet out the associated port
            out_port = self.mac_to_port[dest]

            log.debug("  S{} - Installing flow: {} Port {} -> {} Port {}".format(self.switch_id, source, packet_in.in_port, dest, out_port))

            # Set fields to match received packet
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet_in)
            msg.idle_timeout = 100
            msg.hard_timeout = 1000
            msg.actions.append(of.ofp_action_output(port = out_port))
            self.connection.send(msg)
            self.resend_packet(packet_in, out_port)

        else:
            if self.is_core():
                # Flood the packet out to the edge switch ports
                log.debug("  S{} - Flooding packet from {} {} to edge switch ports".format(self.switch_id, source, packet_in.in_port))
                self.resend_packet(packet_in, of.OFPP_FLOOD)
            
            # Switch is an edge switch and gets a packet from a core
            elif self.sent_from_core(packet_in.in_port):
                # Flood the packet out to the hosts
                ports = [port for port in range(1, self.nCore + self.nHosts + 1) if port not in self.coreSwitchIDs]
                log.debug("  S{} - Flooding packet from {} {} to host ports :{}".format(self.switch_id, source, packet_in.in_port, ports))
                for p in ports:
                    self.resend_packet(packet_in, out_port=p)
            
            # Switch is an edge switch and gets a packet from a host
            else:
                out_port_to_tenant = self.tenants.getVLAN(packet.src)
                # If host has no tenant yet, assign him a tenant
                if out_port_to_tenant == -1:
                    self.tenants.addToVLAN(packet.src, out_port=self.vlan_id)
                    out_port_to_tenant = self.vlan_id
                    self.vlan_id = (self.vlan_id) % self.tenants.n_vlans + 1
                # Forward the packet from host to core switch on port out_port_to_tenant
                log.debug("  S{} - Forwarding packet from {} {} out to port {}".format(self.switch_id, source, packet_in.in_port, out_port_to_tenant))
                self.resend_packet(packet_in, out_port=out_port_to_tenant)

            print(self.tenants.vlans)

    def _handle_PacketIn (self, event):
        """
        Handles packet in messages from the switch.
        """
        packet = event.parsed
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp
        self.act_like_switch(packet, packet_in)
    

def launch (nCore, nEdge, nHosts):
    """
    Starts the component
    """
    print("Controller started with the following arguments:")
    print("nCore={}, nEdge={}, nHosts ={}".format(nCore, nEdge, nHosts))

    def start_switch (event):
        log.debug("Controlling %s" % (event.connection,))
        VLAN_Controller(event.connection, int(nCore), int(nEdge), int(nHosts))

    core.openflow.addListenerByName("ConnectionUp", start_switch)