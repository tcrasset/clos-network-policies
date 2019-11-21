"""Topology for a simplified Clos-like network."""

from mininet.topo import Topo


class ClosTopo(Topo):
    """Topology for a simplified Clos-like network.

    The topology has one layer of core switches, fully connected to one layer
    of edge switches, each of which has a number of hosts.

    Args:
        nCore: number of core switches
        nEdge: number of edge switches
        nHosts: number of hosts per edge switch
        bw: bandwidth in Mbps
    """

    def build(self, nCore=2, nEdge=3, nHosts=3, bw=10):
        # Add core switches
        coreSwitches = ["s%d" % i for i in range(1, nCore + 1)]
        for core in coreSwitches:
            self.addSwitch(core, isCoreSwitch=True)

        # Add edge switches
        hostNo = 1
        for i in range(nCore + 1, nCore + 1 + nEdge):
            edge = self.addSwitch("s%d" % i)
            # Link edge switch to all core switches
            for core in coreSwitches:
                self.addLink(edge, core, bw=bw)
            # Add a pod of hosts to edge switch
            for j in range(hostNo, hostNo + nHosts):
                host = self.addHost("h%d" % j)
                self.addLink(host, edge, bw=bw)
            hostNo += nHosts


    def coreSwitches(self, sort=True):
        """Return the list of core switches dpids.

        Args:
            sort: sort switches alphabetically
        """
        return [node for node in self.nodes(sort) if self.isCoreSwitch(node)]


    def edgeSwitches(self, sort=True):
        """Return the list of edge switches dpids.

        Args:
            sort: sort switches alphabetically
        """
        return [node for node in self.nodes(sort) if self.isEdgeSwitch(node)]


    def isCoreSwitch(self, node):
        """Returns true if node is a core switch."""
        return self.g.node[node].get("isCoreSwitch", False)


    def isEdgeSwitch(self, node):
        """Returns true if node is an edge switch."""
        return self.isSwitch(node) and not self.isCoreSwitch(node)

topos = {
    'clostopo': (lambda nCore=2, nEdge=3, nHosts=3, bw=10:
                 ClosTopo(nCore=nCore, nEdge=nEdge, nHosts=nHosts, bw=bw))
}
