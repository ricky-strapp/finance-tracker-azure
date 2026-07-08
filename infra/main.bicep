targetScope = 'subscription'

param rgDetails array
param requiredVnets array
param containerRegistryName string
param containerRegistryRG string
param requiredLogAnalyticsWorkspaces array

module resourceGroups './modules/resourceGroups.bicep' = [for item in rgDetails: {
  name:'${item.rgName}-deployment'
  params: {
    rgName: item.rgName
    rgEnvironment: item.rgEnvironment
    rgProject: item.rgProject
    }
}]

module policy './modules/policy.bicep' = [for item in rgDetails: {
  name: '${item.rgEnvironment}-policy'
  scope: resourceGroup(item.rgName)
  dependsOn: [
    resourceGroups
  ]
}]

module networking './modules/networking.bicep' = [for item in requiredVnets: {
  name: item.vnetName
  scope: resourceGroup(item.rgName)
  params: {
    vnetName: item.vnetName
    vnetAddressSpace: item.vnetAddressSpace
    subnetAddressSpace: item.subnetAddressSpace
  }
  dependsOn: [
    resourceGroups
  ]
}]

module containerRegistry './modules/containerRegistry.bicep' = {
  name: 'fintrack-container-registry-deployment'
  scope: resourceGroup(containerRegistryRG)
  params: {
    resourceName: containerRegistryName
  }
  dependsOn: [
    resourceGroups
  ]
}

module logAnalytics './modules/logAnalytics.bicep' = [for item in requiredLogAnalyticsWorkspaces: {
  name: item.workspaceName
  scope: resourceGroup(item.rgName)
  params: {
    workspaceName: item.workspaceName
    workspaceSku: item.workspaceSku
  }
  dependsOn: [
    resourceGroups
  ]
}]
