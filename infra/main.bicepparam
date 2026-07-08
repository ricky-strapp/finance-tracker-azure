using 'main.bicep'

param rgDetails = [
  {
    rgName: 'rg-fintrack-personal-uksouth'
    rgEnvironment: 'Personal'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-shared-uksouth'
    rgEnvironment: 'Shared'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-demo-uksouth'
    rgEnvironment: 'Demo'
    rgProject: 'Finance-Tracker'
  }
]

param requiredVnets = [
  {
    vnetName: 'vnet-fintrack-personal-uksouth'
    vnetAddressSpace: '10.0.0.0/16'
    subnetAddressSpace: '10.0.0.0/24'
    rgName: 'rg-fintrack-personal-uksouth'
  }
  {
    vnetName: 'vnet-fintrack-demo-uksouth'
    vnetAddressSpace: '10.1.0.0/16'
    subnetAddressSpace: '10.1.0.0/24'
    rgName: 'rg-fintrack-demo-uksouth'
  }
]

param containerRegistryName = 'fintrackcontainerregistry01'
