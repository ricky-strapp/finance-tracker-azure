targetScope = 'resourceGroup'

param resourceName string

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: resourceName
  location: resourceGroup().location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}
