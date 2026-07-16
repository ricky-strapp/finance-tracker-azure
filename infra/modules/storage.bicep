targetScope = 'resourceGroup'

param location string
param storageName string
param fileShareName string

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
