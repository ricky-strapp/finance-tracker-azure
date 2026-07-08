targetScope = 'resourceGroup'

param vnetName string
param vnetAddressSpace string
param subnetAddressSpace string

var subnetName = 'snet-containerapps'

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2025-01-01' = {
  name: vnetName
  location: resourceGroup().location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressSpace
      ]
    }
  }

  resource subnet1 'subnets' = {
    name: subnetName
    properties: {
      addressPrefix: subnetAddressSpace
      delegations: [
        {
          name: 'containerapps-delegation'
          properties: {
            serviceName: 'Microsoft.App/environments'
          }
        }
      ]
    }  }
}

output subnet1ResourceId string = virtualNetwork::subnet1.id
