targetScope = 'subscription'

param location string
param rgName string
param rgEnvironment string
param rgProject string

resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: location
  tags: {
      Environment: rgEnvironment
      Project: rgProject
    }
}
