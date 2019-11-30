
from pox.core import core

class Tenants(object):
    """Object holding information about hosts and tenants in a VLAN.
    
    Arguments
    ----------
    self.vlans: dict of EthAddr: int
        Mapping of MAC_Address to vlan_id

    """
    def __init__(self, n_vlans):
        """Initializes the Tree_Controller object.

        Parameters
        ----------
        n_vlans : int
            Total number of different VLANs
        """

        self.vlans = {}
        self.n_vlans = n_vlans

    def addToVLAN(self, address, vlan_id):
        """Adds a mapping from MAC address to vlan_id in the dictionnary.

        Parameters
        ----------
        address : EthAddr
            MAC_Address of a host
        vlan_id : int
            ID specifying to which tenant a host belongs
        
        Returns
        ----------
        None
        """

        self.vlans[address] = vlan_id
        return

    def getVLAN(self, address):
        """Returns VLAN ID of a given host MAC address.

        Parameters
        ----------
        address : EthAddr
            MAC_Address of a host
        
        Returns
        ----------
        int
            The vlan_id associated to the address or
            -1 if None is found.
        """

        if(address in self.vlans):
            return self.vlans[address]
        else:
            return -1