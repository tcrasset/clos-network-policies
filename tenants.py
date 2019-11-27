
from pox.core import core

class Tenants(object):
    def __init__(self, n_vlans: int):
        self.vlans = {}
        self.n_vlans = n_vlans

    def addToVLAN(self, address: EthAddr, tenant: int):

        self.vlans[address] = tenant

    def getVLAN(self, address: EthAddr):
        if(address in self.vlans):
            return self.vlans[address]
        else:
            print("Host does not belong to any VLAN")
            return -1