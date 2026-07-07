targetScope = 'subscription'

param rgName string
param rgEnvironment string
param rgProject string

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: 'uksouth'
  tags: {
      Environment: rgEnvironment
      Project: rgProject
    }
}
