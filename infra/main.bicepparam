using 'main.bicep'

param location = 'ukwest'

param rgDetails = [
  {
    rgName: 'rg-fintrack-personal-${location}'
    rgEnvironment: 'Personal'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-demo-${location}'
    rgEnvironment: 'Demo'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-shared-${location}'
    rgEnvironment: 'Shared'
    rgProject: 'Finance-Tracker'
  }
]

param requiredVnets = [
  {
    vnetName: 'vnet-fintrack-personal-${location}'
    vnetAddressSpace: '10.0.0.0/16'
    subnetAddressSpace: '10.0.0.0/24'
    rgName: 'rg-fintrack-personal-${location}'
  }
  {
    vnetName: 'vnet-fintrack-demo-${location}'
    vnetAddressSpace: '10.1.0.0/16'
    subnetAddressSpace: '10.1.0.0/24'
    rgName: 'rg-fintrack-demo-${location}'
  }
]

param containerRegistryName = 'fintrackcontainerregistry01'
param containerRegistryRG = 'rg-fintrack-shared-${location}'

param requiredLogAnalyticsWorkspaces = [
  {
    workspaceName: 'law-fintrack-personal-${location}'
    rgName: 'rg-fintrack-personal-${location}'
    workspaceSku: 'PerGB2018'
  }
  {
    workspaceName: 'law-fintrack-demo-${location}'
    rgName: 'rg-fintrack-demo-${location}'
    workspaceSku: 'PerGB2018'
  }
]

param requiredManagedEnvironments = [
  {
    managedEnvironmentName: 'me-fintrack-personal-${location}'
    rgName: 'rg-fintrack-personal-${location}'
    volumeMount: true
    storageName: 'fintrackstorage01'
    fileShareName: 'fintrack-db-share'
  }
  {
    managedEnvironmentName: 'me-fintrack-demo-${location}'
    rgName: 'rg-fintrack-demo-${location}'
    volumeMount: false
  }
]

param requiredAppServices = [
  {
    appServiceName: 'as-fintrack-personal-${location}'
    rgName: 'rg-fintrack-personal-${location}'
    managedEnvironmentName: 'me-fintrack-personal-${location}'
    volumes: [
      {
        name: 'fintrack-db-volume'
        storageName: 'fintrack-db-mount'
        storageType: 'AzureFile'
      }
    ]
    volumeMounts: [
      {
        volumeName: 'fintrack-db-volume'
        mountPath: '/app/database'
      }
    ]
  }
  {
    appServiceName: 'as-fintrack-demo-${location}'
    rgName: 'rg-fintrack-demo-${location}'
    managedEnvironmentName: 'me-fintrack-demo-${location}'
    volumes: []
    volumeMounts: []
  }
]
