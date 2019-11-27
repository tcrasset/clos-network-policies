
from pox.core import core

class Tenants(object):
    def __init__(self, n_vlans):
        self.vlans = {}
        self.n_vlans = n_vlans

    def addToVLAN(self, address, out_port):
        self.vlans[address] = out_port

    def getVLAN(self, address):
        if(address in self.vlans):
            return self.vlans[address]
        else:
            print("Host {} does not belong to any VLAN".format(address))
            return -1