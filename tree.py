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
# Modified for the course of Network Infrastructures at 2019/2020 at 
# University of Liege to implement a Spanning Tree Controller Policy


from pox.core import core
import pox.openflow.libopenflow_01 as of
import clos-test/clostopo as clostopo

log = core.getLogger()


class Tree_Controller(object):
  """
  A Tree_Policy object is created for each switch that connects.
  A Connection object for that switch is passed to the __init__ function.
  """
  def __init__ (self, connection):
    # Keep track of the connection to the switch so that we can
    # send it messages!
    self.connection = connection
    self.topology = clostopo
    # This binds our PacketIn event listener
    connection.addListeners(self)

    # Use this table to keep track of which ethernet address is on
    # which switch port (keys are MACs, values are ports).
    self.mac_to_port = {}
  

  def delete_flow(self, datapath):
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser

    for dst in self.mac_to_port[datapath.id].keys():
      match = parser.OFPMatch(eth_dst=dst)
      mod = parser.OFPFlowMod(
        datapath, command=ofproto.OFPFC_DELETE,
        out_port=ofproto.ofp_packet_ANY, out_group=ofproto.OFPG_ANY,
        priority=1, match=match
      )



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

    # Add to dictionnary
    self.mac_to_port[source] = packet_in.in_port
    
    if dest in self.mac_to_port:
      # Send packet out the associated port
      out_port = self.mac_to_port[dest]
      log.debug("Installing flow...")
      log.debug("{} Port {} -> {} Port {} ".format(source, packet_in.in_port, dest, out_port))

      msg = of.ofp_flow_mod()

      # Set fields to match received packet
      msg.match = of.ofp_match.from_packet(packet)
      #
      #< Set other fields of flow_mod (timeouts? buffer_id?) >
      msg.idle_timeout = 1
      msg.hard_timeout = 10
      msg.actions.append(of.ofp_action_output(port = out_port))
      self.connection.send(msg)
      self.resend_packet(packet_in, out_port)

    else:
      # Flood the packet out everything but the input port
      self.resend_packet(packet_in, of.OFPP_FLOOD)

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

def launch ():
  """
  Starts the component
  """
  def start_switch (event):
    log.debug("Controlling %s" % (event.connection,))
    Tree_Controller(event.connection)
  core.openflow.addListenerByName("ConnectionUp", start_switch)