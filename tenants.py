
from pox.core import core
import clos-test/clostopo as clostopo
from mininet.topo import Topo
import random

class Tenants(object):
    def __init__(self, topology: Topo, n_vlans: int):
        self.topology = topology
        self.vlans = {}
        self.n_vlans = n_vlans

    def addToVLAN(self, address: EtherAddr, tenant: int):
        self.vlans[address] = tenant

    def getVLAN(self, address: EtherAddr):
        if(address in self.vlans):
            return self.vlans[address]
        else:
            vlan_id = random.randint(0, n_vlans)
            self.addToVLAN(address, vlan_id)
            return vlan_id

        

