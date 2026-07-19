targetScope = 'resourceGroup'

param location string
param storageName string
param fileShareName string
param existingManagedEnvironmentName string

resource storageAccount 'Microsoft.Storage/storageAccounts@2026-04-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2026-04-01' = {
  parent: storageAccount
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2026-04-01' = {
  parent: fileService
  name: fileShareName
}

resource existingManagedEnvironment 'Microsoft.App/managedEnvironments@2025-07-01' existing = {
 name: existingManagedEnvironmentName
}

resource containerAppStorage 'Microsoft.App/managedEnvironments/storages@2026-01-01' = {
  parent: existingManagedEnvironment
  name: 'fintrack-db-mount'
  properties: {
    azureFile: {
      accessMode: 'ReadWrite'
      accountKey: storageAccount.listKeys().keys[0].value
      accountName: storageName
      shareName: fileShareName
    }
  }
}
