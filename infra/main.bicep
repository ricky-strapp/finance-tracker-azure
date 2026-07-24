targetScope = 'subscription'

param location string
param rgDetails array
param requiredVnets array
param containerRegistryName string
param containerRegistryRG string
param requiredLogAnalyticsWorkspaces array
param requiredManagedEnvironments array
param requiredAppServices array
param vaultName string
param vaultRG string
param policyName string
param keyName string
param keyRG string

module resourceGroups './modules/resourceGroups.bicep' = [for item in rgDetails: {
  name:'${item.rgName}-deployment'
  params: {
    location: location
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

var workspaceRGNames = map(requiredLogAnalyticsWorkspaces, ws => ws.rgName)
var networkRGNames = map(requiredVnets, vnet => vnet.rgName)

module managedEnvironments './modules/managedEnvironments.bicep' = [for item in requiredManagedEnvironments: {
  name: '${item.managedEnvironmentName}-deployment'
  scope: resourceGroup(item.rgName)
  params: {
    workspaceName: logAnalytics[indexOf(workspaceRGNames, item.rgName)].outputs.workspaceName
    managedEnvironmentName: item.managedEnvironmentName
    workspaceCustomerId: logAnalytics[indexOf(workspaceRGNames, item.rgName)].outputs.workspaceCustomerId
    workspaceRgName: item.rgName
    subnetResourceId: networking[indexOf(networkRGNames, item.rgName)].outputs.subnet1ResourceId
  }
  dependsOn: [
    logAnalytics
    networking
  ]
}]

module identity './modules/identity.bicep' = {
  name: 'identity-deployment'
  scope: resourceGroup(containerRegistryRG)
  params: {
    location: location
    containerRegistryName: containerRegistryName
    identityName: 'fintrack-identity'
  }
  dependsOn: [
    containerRegistry
  ]
}

module storageAccount './modules/storage.bicep' = [for item in requiredManagedEnvironments: if(item.volumeMount == true) {
  name: '${item.storageName}-deployment'
  scope: resourceGroup(item.rgName)
  params:{
    storageName: item.storageName
    location: location
    fileShareName: item.fileShareName
    existingManagedEnvironmentName: item.managedEnvironmentName
  }
  dependsOn: [
    managedEnvironments
  ]
}]

module containerApps './modules/containerApp.bicep' = [for item in requiredAppServices: {
  name: '${item.appServiceName}-deployment'
  scope: resourceGroup(item.rgName)
  params: {
    resourceName: item.appServiceName
    location: location
    managedEnvironmentId: '/subscriptions/${subscription().subscriptionId}/resourceGroups/${item.rgName}/providers/Microsoft.App/managedEnvironments/${item.managedEnvironmentName}'
    identityID: identity.outputs.identityId
    containerRegistryName: '${containerRegistryName}.azurecr.io'
    containerImage: '${containerRegistryName}.azurecr.io/finance-tracker:latest'
    volumes: item.volumes
    volumeMounts: item.volumeMounts 
  }
  dependsOn: [
    managedEnvironments
    storageAccount
  ]
}]

module recoveryVault './modules/recoveryVault.bicep' = {
  name: '${vaultName}-deployment'
  scope: resourceGroup(vaultRG)
  params: {
    resourceName: vaultName
    location: location
    policyName: policyName
  }
}

module keyVault './modules/keyVault.bicep' = {
  name: '${keyName}-deployment'
  scope: resourceGroup(keyRG)
  params: {
    resourceName: keyName
    location: location
    principalId: identity.outputs.principalId
  }
}

